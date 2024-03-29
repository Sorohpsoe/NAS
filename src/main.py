import os
import re
import json
import ipaddress
import shutil
from gns3fy import Gns3Connector, Project
from telnetlib import Telnet
from time import sleep
import sys



def load_data(intention) :
    chemin_data = os.path.join(os.path.dirname(__file__),'..','data',intention)

    with open(chemin_data,"r") as data :
        intentions = json.load(data)          

    return intentions


def supprimer_fichiers(dossier):
    repertoire_script = os.path.dirname(__file__)

    # Construire le chemin complet pour le dossier "config_files"
    dossier_a_purger = os.path.join(repertoire_script, "config_files")

    # Liste tous les fichiers dans le dossier
    fichiers_dans_dossier = os.listdir(dossier_a_purger)

    # Construit le chemin complet pour chaque fichier et le supprime
    for fichier in fichiers_dans_dossier:
        chemin_fichier = os.path.join(dossier_a_purger, fichier)

        if os.path.isfile(chemin_fichier):
            os.remove(chemin_fichier)


def lister_routers(repertoire_projet) :
    ##
    #Trouve les fichiers configs de chaques routeurs dans le repertoire_projet
    ##

    repertoire_courant =  repertoire_projet + "\\project-files\\dynamips"    

    routers_list = {}

    if os.path.exists(repertoire_courant):
        #Création d'une liste avec tous les dossiers des routeurs
        dossiers = [repertoire_courant+"\\"+nom for nom in os.listdir(repertoire_courant) if os.path.isdir(os.path.join(repertoire_courant, nom))]

        for router in dossiers :
            #Création du chemin vers le .cfg
            chemin = router + "\\configs"
            config_file=""
            for nom_fichier in os.listdir(chemin) :

                #Recherche du fichier de config au démarrage
                if nom_fichier.endswith(".cfg") and 'startup' in nom_fichier:
                    config_file = chemin + "\\" + nom_fichier

            #Lecture du .cfg pour determiner à quel router il appartient
            with open(config_file, 'r') as config : 
                config_content = config.read()
                hostname_pattern = r'hostname\s+(\w+)'
                hostname_match = re.search(hostname_pattern,config_content)

                if hostname_match :
                    #Création du dictionnaire avec comme clé le nom du routeur et en valeur le chemin absolu vers le .cfg
                    routers_list[hostname_match.group(1)] = config_file
                else : 
                    print(f"Hostname non trouvé dans le fichier de config :{router}")
  
    
    return routers_list
        
def adressage(data):

    index = 0

    for AS in data["AS"]:
        if data["AS"][AS]["client"] == "False" :
    
            adresse=data["AS"][AS]["plage_IP"]["interfaces_physique"]
            nombre_liens=len(data["AS"][AS]["liens"])

            adresses_physiques = adressage_auto(adresse,nombre_liens)


            # Créer une plage d'adresses pour chaque lien
            for i in range(nombre_liens):
                


                for j in range(2) :

                    data["AS"][AS]["liens"][i][j][1] = "GigabitEthernet" + data["AS"][AS]["liens"][i][j][1][1:]
            
                    data["AS"][AS]["liens"][i][j].append(adresses_physiques[i][j])


            for i in range(len(data["AS"][AS]["liens"])) : 
                for j in range(2) : 

                    dico = {"nom":data["AS"][AS]["liens"][i][j][0],data["AS"][AS]["liens"][i][j][1]:data["AS"][AS]["liens"][i][j][2]}
                    data["AS"][AS]["liens"][i][j] = dico


            nb_routeurs = len(data["AS"][AS]["routeurs"])


            plage = data["AS"][AS]["plage_IP"]["interfaces_loopback"]

            adresses_loopback = adressage_loopback(plage,nb_routeurs)


            for i in range(nb_routeurs) :
                data["AS"][AS]["routeurs"][i]["Loopback0"] = adresses_loopback[i]
        
        else :
        
            for AS_autre in data["AS"] :

                if data["AS"][AS_autre]["client"] == "True" :

                    if data["AS"][AS_autre]["num_client"] == data["AS"][AS]["num_client"] :

                        
                        if "rt" in data["AS"][AS_autre].keys() :
                            data["AS"][AS]["rt"] = data["AS"][AS_autre]["rt"]
                            data["AS"][AS]["rd"] = data["AS"][AS_autre]["rd"]
                        else :
                            index += 1
                            data["AS"][AS]["rd"] = index
                            index += 1
                            data["AS"][AS]["rt"] = index



def recherche_bordures(data) :

    for MPLS in data["liens_MPLS"] :
        MPLS["client"][1] ="GigabitEthernet"+MPLS["client"][1][1:]
        MPLS["fournisseur"][1] ="GigabitEthernet"+MPLS["fournisseur"][1][1:]


    for AS in data["AS"] :

        new_routeurs = []

        for router in data["AS"][AS]["routeurs"] :

            bordure = False

            for MPLS in data["liens_MPLS"] :

                
                if router == MPLS["client"][0] :
                    new_routeurs.append({"nom":router,"etat":"bordure"})
                    bordure = True
                elif not bordure and router == MPLS["fournisseur"][0] :
                    new_routeurs.append({"nom":router,"etat":"bordure"})
                    bordure = True
            
            if not bordure :
                new_routeurs.append({"nom":router,"etat":"interne"})
        
        data["AS"][AS]["routeurs"] = new_routeurs






def constante(router):

    config = f"""!
version 15.2
service timestamps debug datetime msec
service timestamps log datetime msec
!
hostname {router}
!
boot-start-marker
boot-end-marker
!
!

!"""

    commande("\n", router)
    commande("\n", router)
    commande("\n", router)

    sleep(1)

    commande("conf t", router)
    commande("unicast-routing",router)
    commande("end",router)



    # Obtenir le chemin complet du fichier dans le dossier config_files
    filename = os.path.join(os.path.dirname(__file__), "config_files", router + ".cfg")

    # Écrire la configuration dans le fichier spécifié
    with open(filename, 'w') as fichier:
        fichier.write(config)

    
def vrf (routeur,liste_vrf) :
    texte =  ""

    for vrf in liste_vrf : 
        texte += f"""\nvrf definition {vrf[0]}
 rd 100:{vrf[1]}
 route-target export 100:{vrf[2]}
 route-target import 100:{vrf[2]}
 !
 address-family ipv4
 exit-address-family
!
"""
    
    texte += """!
no aaa new-model
no ip icmp rate-limit unreachable
ip cef
!
!
!
no ip domain lookup
!
!
multilink bundle-name authenticated
!
!
!
ip tcp synwait-time 5
! 
!
!
"""
    filename = os.path.join(os.path.dirname(__file__), "config_files", routeur + ".cfg")

    with open(filename, 'a') as fichier:
        fichier.write(texte)



def conf_interface(routeur,interface,IGP,adresse,forwarding=None):

    # Créer la configuration d'une interface 


    texte = f"""\ninterface {interface}"""
    if forwarding != None :
        texte += f"""\nvrf forwarding {forwarding}"""

    if interface == "Loopback0" :
        texte +=f"""\n ip address {adresse} 255.255.255.255"""
    else : 
        texte +=f"""\n ip address {adresse} 255.255.255.252"""

    if forwarding == None :
        texte+=f"\n ip ospf {routeur[1:]} area 0\n"




    #A changer
    if interface!="Loopback0":
        texte+=""" \n negotiation auto
 mpls ip"""
 
    texte += "\n!"
    #Envoi des commande avec telnet

    commande("conf t",routeur)
    commande(f"interface {interface}",routeur)
    if forwarding != None :
        commande(f"vrf forwarding {forwarding}",routeur)

    #A refaire
    #commande(f"ip address {adresse} {subnet_mask}",routeur)

    if forwarding == None :
        commande(f"ip ospf {routeur[1:]} area 0",routeur)

    if interface != "Loopback0" :
        commande("negotiation auto",routeur)
        commande("mpls ip",routeur)

    commande("no shutdown",routeur)




    if IGP == "RIP" :
        commande(f"rip connected enable",routeur)
    elif IGP == "OSPF" :
        commande(f"ospf {routeur[1:]} area 0",routeur)

    commande("no shutdown",routeur)

    commande("end",routeur)


    # Ouvrir le fichier et ajouter les informations à la fin
    filename = os.path.join(os.path.dirname(__file__), "config_files", routeur + ".cfg")

    with open(filename, 'a') as fichier:
        fichier.write(texte)



def conf_vpn(nom_routeur,AS,loopbacks_voisin,clients,client,own = [],bordure = False ):
    
    if client == "True" : AS = 1

    texte_routeur = f"""\n!\nrouter bgp {AS}
 bgp router-id {nom_routeur[1:]}.{nom_routeur[1:]}.{nom_routeur[1:]}.{nom_routeur[1:]}
 bgp log-neighbor-changes"""
    


    texte_family=f"""\n!\naddress-family ipv4\n"""

    texte_vpn ="""\n!\naddress-family vpnv4"""

    texte_client =""



    for clientt in clients : 
        texte_client += f"""\naddress-family ipv4 vrf {clientt[0]}
 neighbor {clientt[1]} remote-as {clientt[2][2:]}
 neighbor {clientt[1]} activate
exit-address-family
!"""
    
    
    for adresse in loopbacks_voisin:

        texte_routeur+=f"""\n neighbor {adresse[:-3]} remote-as {AS}
 """
        if client == "False":
            texte_routeur += f"neighbor {adresse[:-3]} update-source Loopback0\n"

        for add in own : 
            texte_family += f"network {add[:-3]} mask 255.255.255.252\n"
        
        texte_family+=f"""\n neighbor {adresse[:-3]} activate"""

        if bordure :
            texte_vpn += f"""
    neighbor {adresse[:-3]} activate
    neighbor {adresse[:-3]} send-community both"""

        

    texte_family +=  "\nexit-address-family\n!"
    texte_vpn +=  "\nexit-address-family\n!"





    filename = os.path.join(os.path.dirname(__file__), "config_files", nom_routeur + ".cfg")

    # Écrire la configuration dans le fichier spécifié
    with open(filename, 'a') as fichier:
        fichier.write(texte_routeur)
        fichier.write(texte_family)
        if client == "False" and bordure :
            fichier.write(texte_vpn)
            fichier.write(texte_client)
    
             
 
 
    
def conf_igp(nom,IGP,addresses) :
    texte="""
!
ip forward-protocol nd
!
!
no ip http server
no ip http secure-server
!"""    
    if IGP == "RIP" :

        texte += """
router rip connected
 redistribute connected
"""
    else :
        texte += f"""
router ospf {nom[1:]}
 router-id {nom[1:]}.{nom[1:]}.{nom[1:]}.{nom[1:]}
 passive-interface Loopback0
"""
        
    for address in addresses :
        texte += f""" network {address[:-3]} 0.0.0.3 area 0
"""

   





    filename = os.path.join(os.path.dirname(__file__), "config_files", nom + ".cfg")

    # Écrire la configuration dans le fichier spécifié
    with open(filename, 'a') as fichier:
        fichier.write(texte)






def logic(data) :

    supprimer_fichiers("config_files")

    #Mise en place du json complet
    recherche_bordures(intentions)
    adressage(intentions)

    for AS in data["AS"] :




        IGP = data["AS"][AS]["IGP"]

        for routeur in data["AS"][AS]["routeurs"] :

            constante(routeur["nom"])

            vrfs = []
            voisins = []
            clients = []
            #  clients = [nom client, adresse client, AS client]

            if data["AS"][AS]["client"] == "True" :
                own = [data["AS"][AS]["addresse"]]
            else : own = []

            interfaces_bordures = []

            if routeur["etat"] == "bordure" :
                is_bordure = True
            else :
                is_bordure = False



            for bordures in data["liens_MPLS"] :
                for bordure in bordures :

                    if bordures[bordure][0] == routeur["nom"] :



                        interfaces_bordures.append(bordures[bordure][1])    

                        if bordure == "client" :
                            j = "fournisseur"
                        else : 
                            j = "client"


                        nom_autre = None
                        if data["AS"][AS]["client"] == "False" :
                            nom_autre = bordures[j][0]
                            for AS_autre in data["AS"] :
                                for routeur_autre in data["AS"][AS_autre]["routeurs"] :
                                    if routeur_autre["nom"] == nom_autre :

                                        nom_vpn = data["AS"][AS_autre]["num_client"]

                                        vrfs.append([nom_vpn,data["AS"][AS_autre]["rd"],data["AS"][AS_autre]["rt"]])

                                        clients.append([nom_vpn,bordures[j][2],AS_autre])

                        else :
                            own.append(bordures[bordure][2]+'/30')


            vrf(routeur["nom"],vrfs)

            if data["AS"][AS]["client"] == "False" :

                conf_interface(routeur["nom"],"Loopback0",IGP,routeur["Loopback0"][:-3])

            else : 

                conf_interface(routeur["nom"],"GigabitEthernet1/0",IGP,data["AS"][AS]["addresse"][:-3])

            loopback_voisins = []

            for bordures in data["liens_MPLS"] :
                for bordure in bordures :
                    if bordures[bordure][0] == routeur["nom"] :
                        nom_autre = None
                        if data["AS"][AS]["client"] == "False" :
                            nom_autre = bordures[j][0]
                            for AS_autre in data["AS"] :
                                for routeur_autre in data["AS"][AS_autre]["routeurs"] :
                                    if routeur_autre["nom"] == nom_autre :

                                        nom_vpn = data["AS"][AS_autre]["num_client"]
                                        conf_interface(routeur["nom"],bordures[bordure][1],IGP,bordures[bordure][2],nom_vpn)

                        else : 
                            conf_interface(routeur["nom"],bordures[bordure][1],IGP,bordures[bordure][2])

                            loopback_voisins.append(bordures[j][2])



            addresses_router = []

            for lien in data["AS"][AS]["liens"] :
                for routeur_in_lien in lien :
                    if type(routeur_in_lien) ==  dict :
                    
                        if routeur_in_lien["nom"] == routeur["nom"] :

                            addresses_router.append(routeur_in_lien[list(routeur_in_lien.keys())[1]])

                            interface = list(routeur_in_lien.keys())[1]
                            conf_interface(routeur["nom"],interface,IGP,routeur_in_lien[interface][:-3])
                        else : 
                            voisins.append(routeur_in_lien["nom"])
            

            for voisin_lb in data["AS"][AS]["routeurs"] :
                if voisin_lb["nom"] in voisins :
                    loopback_voisins.append(voisin_lb["Loopback0"])

            if data["AS"][AS]["client"] == "False" :
                conf_igp(routeur["nom"],IGP,addresses_router)



            conf_vpn(routeur["nom"],AS[2:],loopback_voisins,clients,data["AS"][AS]["client"],own,is_bordure)

    # Write the data to NAS/data/complet.json
    complet_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'complet.json')
    with open(complet_file, 'w') as complet_data:
        json.dump(data, complet_data)

def adressage_auto(plage, nb_lien):
    plages = []
    subnet = ipaddress.ip_network(plage)
    subnet_size = subnet.num_addresses

    if subnet_size >= nb_lien * 4:
        for i in range(nb_lien):

            IP1 = str(subnet.network_address + i * 4 + 1) + "/30"
            IP2 = str(subnet.network_address + i * 4 + 2) + "/30"

            plages.append([IP1,IP2])

    return plages


def adressage_loopback(plage, nb_routeur):
    plages = []
    subnet = ipaddress.ip_network(plage)
    subnet_size = subnet.num_addresses


    if subnet_size >= nb_routeur:
        for i in range(nb_routeur):
            plages.append(str(subnet.network_address + i) + "/32")
    else : 
        print("Pas assez d'adresses pour les loopbacks")

    return plages


def drag_and_drop(repertoire_projet) :
    dossiers = lister_routers(repertoire_projet)
    for routeur,chemin in dossiers.items() :
        shutil.copy(os.path.join(os.path.dirname(__file__), "config_files",routeur+".cfg"),chemin)

def start_telnet(projet_name) :
    serveur = Gns3Connector("http://localhost:3080")
    projet = Project(projet_name, connector=serveur)
    projet.get()
    projet.open()

    noeuds = {}
    for noeud in projet.nodes :
        noeuds[noeud.name] = Telnet(noeud.console_host,str(noeud.console))

    return noeuds

def commande(cmd,routeur) :

    global noeuds,envoi_telnet

    if envoi_telnet :
        noeuds[routeur].write(bytes(cmd+"\r",encoding="ascii"))

        sleep(0.1)





repertoire_projet = "C:\\Users\\Gauthier\\GNS3\\projects\\vrf"
json_file = "C:\\Users\\Gauthier\\Desktop\\TC\\TC3\\PROJETS_S2\\NAS\\NAS\\data\\data.json"
project_name = os.path.basename(repertoire_projet)

intentions = load_data(json_file)

envoi_telnet = False

if envoi_telnet :
    noeuds = start_telnet(project_name)

logic(intentions)

drag_and_drop(repertoire_projet)