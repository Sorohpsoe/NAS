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
    
    for AS in data["AS"]:
        if data["AS"][AS]["client"] == "False" :
    
            adresse=data["AS"][AS]["plage_IP"]["interfaces_physique"]
            nombre_liens=len(data["AS"][AS]["liens"])

            adresses_physiques = adressage_auto(adresse,nombre_liens)

            # Créer une plage d'adresses pour chaque lien
            for i in range(nombre_liens):
                
                data["AS"][AS]["liens"][i].append(adresses_physiques[i])

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
vrf definition Client_A
 rd 100:110
 !
 address-family ipv4
 exit-address-family
!
!
no aaa new-model
no ip icmp rate-limit unreachable
ip cef
!
!
!
!
!
!
no ip domain lookup
no ipv6 cef
!
!
multilink bundle-name authenticated
!"""

    commande("\n", router)
    commande("\n", router)
    commande("\n", router)

    sleep(1)

    commande("conf t", router)
    commande("ipv6 unicast-routing",router)
    commande("end",router)



    # Obtenir le chemin complet du fichier dans le dossier config_files
    filename = os.path.join(os.path.dirname(__file__), "config_files", router + ".cfg")

    # Écrire la configuration dans le fichier spécifié
    with open(filename, 'w') as fichier:
        fichier.write(config)

        
def conf_interface(routeur,interface,IGP,adresse,forwarding=None):

    # Créer la configuration d'une interface 
    subnet = ipaddress.ip_network(adresse)
    subnet_mask = str(subnet.netmask)
    print(forwarding)
    texte = f"""\ninterface {interface}"""
    if forwarding != None :
        texte += f"""\nvrf forwarding {forwarding}"""

    texte +=f"""\n ip address {adresse} {subnet_mask}"""

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

    commande(f"ip address {adresse} {subnet_mask}",routeur)

    if forwarding == None :
        commande(f"ip ospf {routeur[1:]} area 0",routeur)

    if interface != "Loopback0" :
        commande("negotiation auto",routeur)
        commande("mpls ip",routeur)

    commande("no shutdown",routeur)




    if IGP == "RIP" :
        commande(f"ipv6 rip connected enable",routeur)
    elif IGP == "OSPF" :
        commande(f"ipv6 ospf {routeur[1:]} area 0",routeur)

    commande("no shutdown",routeur)

    commande("end",routeur)


    # Ouvrir le fichier et ajouter les informations à la fin
    filename = os.path.join(os.path.dirname(__file__), "config_files", routeur + ".cfg")

    with open(filename, 'a') as fichier:
        fichier.write(texte)



def conf_vpn(nom_routeur,AS,loopbacks_voisin,clients):

    texte_routeur = f"""\nrouter bgp {AS}
 bgp router-id {nom_routeur[1:]}.{nom_routeur[1:]}.{nom_routeur[1:]}.{nom_routeur[1:]}
 bgp log-neighbor-changes"""
    
    texte_family=f"""\naddress-family ipv4"""

    texte_vpn ="""\n address-family vpnv4"""

    texte_client =""


    for client in clients : 
        texte_client += f"""\n address-family ipv4 vrf {client[2]}
   neighbor {client[0]} remote-as {client[1]}
   neighbor {client[0]} activate
   exit-address-family
!"""
    
    
    for adresse in loopbacks_voisin:

        texte_routeur+=f"""\n neighbor {adresse[:-4]} remote-as {AS}
 neighbor {adresse[:-4]} update-source Loopback0"""
        
        texte_family+=f"""\n  neighbor {adresse[:-4]} activate"""

        texte_vpn += f"""
    neighbor {adresse[:-4]} activate
    neighbor {adresse[:-4]} send-community both
"""

        

    texte_family +=  "\nexit-address-family"
    texte_vpn +=  "\nexit-address-family"





    filename = os.path.join(os.path.dirname(__file__), "config_files", nom_routeur + ".cfg")

    # Écrire la configuration dans le fichier spécifié
    with open(filename, 'a') as fichier:
        fichier.write(texte_routeur)
        fichier.write(texte_family)
        fichier.write(texte_vpn)
        fichier.write(texte_client)
    
             
 
 
    
def conf_igp(nom,IGP,bordures) :
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
ipv6 router rip connected
 redistribute connected
"""
    else :
        texte += f"""
ipv6 router ospf {nom[1:]}
 router-id {nom[1:]}.{nom[1:]}.{nom[1:]}.{nom[1:]}
 passive-interface Loopback0
"""
        
        for bordure in bordures :
            texte +=f""" passive-interface {bordure}
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
            voisins = []
            clients = []
            #  clients = [nom client, adresse client, AS client]

            interfaces_bordures = []

            if data["AS"][AS]["client"] == "False" :
                conf_interface(routeur["nom"],"Loopback0",IGP,routeur["Loopback0"])

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

                        

                        if data["AS"][AS]["client"] == "False" :

                            voisin = [bordures[j][2]]
                            for AS_bordure in data["AS"] :
                                for routeur_bordure in data["AS"][AS_bordure]["routeurs"] :
                                    if routeur_bordure["nom"] == bordures[j][0] :
                                        num_AS = AS_bordure[2:]
                                        voisin.append(num_AS)


                            if data["AS"][AS]["client"] == "False" :
    
                                for AS_voisin in data["AS"][AS]["voisins"] :
                                    if AS_voisin[2:] == num_AS :
                                        voisin.append(data["AS"][AS]["voisins"][AS_voisin])

                        conf_interface(routeur["nom"],bordures[bordure][1],IGP,bordures[bordure][2],nom_vpn)


                            
                        
                        


            for lien in data["AS"][AS]["liens"] :
                for routeur_in_lien in lien :
                    if type(routeur_in_lien) ==  dict :
                    
                        if routeur_in_lien["nom"] == routeur["nom"] :

                            interface = list(routeur_in_lien.keys())[1]
                            conf_interface(routeur["nom"],interface,IGP,routeur_in_lien[interface])
                        else : 
                            voisins.append(routeur_in_lien["nom"])
            
            loopback_voisins = []

            for voisin_lb in data["AS"][AS]["routeurs"] :
                if voisin_lb["nom"] in voisins :
                    loopback_voisins.append(voisin_lb["Loopback0"])
           

            


            conf_igp(routeur["nom"],IGP,interfaces_bordures)
            
            conf_vpn(routeur["nom"],AS[2:],loopback_voisins,clients)
            
            

def adressage_auto(plage, nb_lien):
    plages = []
    subnet = ipaddress.ip_network(plage)
    subnet_size = subnet.num_addresses

    if subnet_size >= nb_lien * 4:
        for i in range(nb_lien):

            IP1 = str(subnet.network_address + i * 4 + 4) + "/30"
            IP2 = str(subnet.network_address + i * 4 + 8) + "/30"

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





repertoire_projet = "C:\\Users\\Gauthier\\GNS3\\projects\\GNS3_project1"
json_file = "C:\\Users\\Gauthier\\Desktop\\TC\\TC3\\PROJETS_S2\\NAS\\NAS\\data\\data.json"
project_name = os.path.basename(repertoire_projet)

intentions = load_data(json_file)

envoi_telnet = False

if envoi_telnet :
    noeuds = start_telnet(project_name)

logic(intentions)

#drag_and_drop(repertoire_projet)