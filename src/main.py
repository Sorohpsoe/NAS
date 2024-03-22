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
        MPLS["routeur"][1] ="GigabitEthernet"+MPLS["routeur"][1][1:]


    for AS in data["AS"] :

        new_routeurs = []

        for router in data["AS"][AS]["routeurs"] :

            bordure = False

            for MPLS in data["liens_MPLS"] :

                
                if router == MPLS["routeur"][0] :
                    new_routeurs.append({"nom":router,"etat":"bordure"})
                    bordure = True
                elif not bordure and router == MPLS["connecte a"][0] :
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

        
def conf_interface(routeur,interface,IGP,adresse,fowarding=None):

    # Créer la configuration d'une interface 
    subnet = ipaddress.ip_network(adresse)
    subnet_mask = str(subnet.netmask)

    texte = f"""\ninterface {interface}"""
    if fowarding != None :
        texte += f"""vrf forwarding {fowarding}"""

    texte +="""ip address {adresse} {subnet_mask}"""

    if fowarding == None :
        texte+=f"\n ip ospf {routeur[1:]} area 0\n!"


    if interface!="Loopback0":
        texte+="""negotiation auto
 mpls ip"""





    #Envoi des commande avec telnet

    commande("conf t",routeur)
    commande(f"interface {interface}",routeur)
    commande(f"ipv6 enable",routeur)
    commande(f"ipv6 address {adresse}",routeur)

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



def conf_bgp(nom_routeur,AS,loopbacks_voisin,plages,adresses_bordures):

    texte_routeur = f"""\nrouter bgp {AS}
 bgp router-id {nom_routeur[1:]}.{nom_routeur[1:]}.{nom_routeur[1:]}.{nom_routeur[1:]}
 bgp log-neighbor-changes
 no bgp default ipv4-unicast"""
    texte_family=f"""\naddress-family ipv6"""
    for plage in plages :
        texte_family+=f"""\n  network {plage} route-map SET_OWN"""
    
    
    for adresse in loopbacks_voisin:
        texte_routeur+=f"""\n neighbor {adresse[:-4]} remote-as {AS}
 neighbor {adresse[:-4]} update-source Loopback0"""
        texte_family+=f"""\n  neighbor {adresse[:-4]} activate"""
        texte_family+=f"""\n  neighbor {adresse[:-4]} send-community"""
        


    for adresse,num_AS,type in adresses_bordures:
        texte_routeur+=f"""\n neighbor {adresse[:-3]} remote-as {num_AS}"""
        texte_family+=f"""\n  neighbor {adresse[:-3]} activate"""
        texte_family+=f"""\n  neighbor {adresse[:-3]} send-community"""
        if type == "Client" :
            texte_family+=f"""\n  neighbor {adresse[:-3]} route-map SET_CLIENT_IN in"""
            
        elif type == "Fournisseur" :
            texte_family+=f"""\n  neighbor {adresse[:-3]} route-map SET_PROVIDER_IN in"""
            texte_family+=f"""\n  neighbor {adresse[:-3]} route-map OUTWARD out"""
        elif type=="Peer" :
            texte_family+=f"""\n  neighbor {adresse[:-3]} route-map SET_PEER_IN in"""
            texte_family+=f"""\n  neighbor {adresse[:-3]} route-map OUTWARD out"""
        


    commande("conf t",nom_routeur)
    commande(f"router bgp {AS}",nom_routeur)
    commande(f"bgp router-id {nom_routeur[1:]}.{nom_routeur[1:]}.{nom_routeur[1:]}.{nom_routeur[1:]}",nom_routeur)
    commande(f"no bgp default ipv4-unicast",nom_routeur)
    for address in loopbacks_voisin:
        commande(f"neighbor {address[:-4]} remote-as {AS}",nom_routeur)
        commande(f"neighbor {address[:-4]} update-source Loopback0",nom_routeur)
    
    for adresse,num_AS,type in adresses_bordures:
        commande(f"neighbor {adresse[:-3]} remote-as {num_AS}",nom_routeur)

    
    commande(f"address-family ipv6 unicast",nom_routeur)
    for plage in plages :
        commande(f"network {plage} route-map SET_OWN",nom_routeur)
    for adresse in loopbacks_voisin:
        commande(f"neighbor {adresse[:-4]} activate",nom_routeur)
        commande(f"neighbor {adresse[:-4]} send-community",nom_routeur)
    for adresse,num_AS,type in adresses_bordures:
        commande(f"neighbor {adresse[:-3]} activate",nom_routeur)
        commande(f"neighbor {adresse[:-3]} send-community",nom_routeur)
        if type == "Client" :
            commande(f"neighbor {adresse[:-3]} route-map SET_CLIENT_IN in",nom_routeur)
            
        elif type == "Fournisseur" :
            commande(f"neighbor {adresse[:-3]} route-map SET_PROVIDER_IN in",nom_routeur)
            commande(f"neighbor {adresse[:-3]} route-map OUTWARD out",nom_routeur)

        elif type=="Peer" :
            commande(f"neighbor {adresse[:-3]} route-map SET_PEER_IN in",nom_routeur)
            commande(f"neighbor {adresse[:-3]} route-map OUTWARD out",nom_routeur)
           
    commande(f"end",nom_routeur)




    filename = os.path.join(os.path.dirname(__file__), "config_files", nom_routeur + ".cfg")

    # Écrire la configuration dans le fichier spécifié
    with open(filename, 'a') as fichier:
        fichier.write(texte_routeur)
        fichier.write(texte_family)
    
def set_route_map(nom_routeur):
    texte="""!
ip community-list 1 permit 1
ip community-list 2 permit 2
ip community-list 3 permit 3
ip community-list 4 permit 4
!
route-map SET_CLIENT_IN permit 10
 set community 1
 set local-preference 150
!
route-map SET_PEER_IN permit 10
 set community 2
 set local-preference 100
!
route-map SET_PROVIDER_IN permit 10
 set community 3
 set local-preference 50
!
route-map SET_OWN permit 10
 set community 4
!
route-map OUTWARD permit 10
 match community 1
 match community 4
!
control-plane
!
!
line con 0
 exec-timeout 0 0
 privilege level 15
 logging synchronous
 stopbits 1
line aux 0
 exec-timeout 0 0
 privilege level 15
 logging synchronous
 stopbits 1
line vty 0 4
 login
!
!
end
"""
    commande("conf t",nom_routeur)
    commande("ip community-list 1 permit 1",nom_routeur)
    commande("ip community-list 2 permit 2",nom_routeur)
    commande("ip community-list 3 permit 3",nom_routeur)
    commande("ip community-list 4 permit 4",nom_routeur)
    
    commande("route-map SET_CLIENT_IN permit 10",nom_routeur)
    commande("set community 1",nom_routeur)
    commande("set local-preference 150",nom_routeur)
    commande("exit",nom_routeur)
    
    commande("route-map SET_PEER_IN permit 10",nom_routeur)
    commande("set community 2",nom_routeur)
    commande("set local-preference 100",nom_routeur)
    commande("exit",nom_routeur)
    
    commande("route-map SET_PROVIDER_IN permit 10",nom_routeur)
    commande("set community 3",nom_routeur)
    commande("set local-preference 50",nom_routeur)
    commande("exit",nom_routeur)
    
    commande("route-map SET_OWN permit 10",nom_routeur)
    commande("set community 4",nom_routeur)
    commande("exit",nom_routeur)
    
    commande("route-map OUTWARD permit 10",nom_routeur)
    commande("match community 1",nom_routeur)
    commande("match community 4",nom_routeur)
    commande("exit",nom_routeur)
    
    commande("end",nom_routeur)
    
    filename = os.path.join(os.path.dirname(__file__), "config_files", nom_routeur + ".cfg")

    # Écrire la configuration dans le fichier spécifié
    with open(filename, 'a') as fichier:
        fichier.write(texte)
             
 
 
    
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
   
    if IGP == "RIP" :
        commande("conf t", nom)
        commande("ipv6 router rip connected",nom)
        commande("redistribute connected",nom)

    else :
        commande("conf t", nom)
        commande(f"ipv6 router ospf {nom[1:]}",nom)
        commande(f"router-id {nom[1:]}.{nom[1:]}.{nom[1:]}.{nom[1:]}",nom)
        commande(f"passive-interface Loopback0",nom)

        for bordure in bordures :
            commande(f"passive-interface {bordure}",nom)

    commande("end",nom)





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

        if data["AS"][AS]["client"] == "False" :

            plages_addresses = []   
            print(data["AS"][AS]["liens"])
            for lien in data["AS"][AS]["liens"] :
                plages_addresses.append(lien[2])


        IGP = data["AS"][AS]["IGP"]

        for routeur in data["AS"][AS]["routeurs"] :

            constante(routeur["nom"])
            voisins = []
            addresses_bordures = []
            interfaces_bordures = []
            conf_interface(routeur["nom"],"Loopback0",IGP,routeur["Loopback0"])

            for bordures in data["liens_MPLS"] :
                for bordure in bordures :
                    if bordures[bordure][0] == routeur["nom"] :
                        conf_interface(routeur["nom"],bordures[bordure][1],IGP,bordures[bordure][2])

                        interfaces_bordures.append(bordures[bordure][1])    

                        if bordure == "routeur" :
                            j = "connecte a"
                        else : 
                            j = "routeur"

                        voisin = [bordures[j][2]]
                        for AS_bordure in data["AS"] :
                            for routeur_bordure in data["AS"][AS_bordure]["routeurs"] :
                                if routeur_bordure["nom"] == bordures[j][0] :
                                    num_AS = AS_bordure[2:]
                                    voisin.append(num_AS)
                        
                        for AS_voisin in data["AS"][AS]["voisins"] :
                            if AS_voisin[2:] == num_AS :
                                voisin.append(data["AS"][AS]["voisins"][AS_voisin])
                        
                        
                        
                        addresses_bordures.append(voisin)

            for lien in data["AS"][AS]["liens"] :
                for routeur_in_lien in lien :
                    if type(routeur_in_lien) ==  dict :
                    
                        if routeur_in_lien["nom"] == routeur["nom"] :

                            interface = list(routeur_in_lien.keys())[1]
                            conf_interface(routeur["nom"],interface,IGP,routeur_in_lien[interface])
                        else : 
                            voisins.append(routeur_in_lien["nom"])
            
            loopback_voisins = []

            for voisin in data["AS"][AS]["routeurs"] :
                if voisin["nom"] in voisins :
                    loopback_voisins.append(voisin["Loopback0"])
           
            
            conf_bgp(routeur["nom"],AS[2:],loopback_voisins,plages_addresses,addresses_bordures)

            conf_igp(routeur["nom"],IGP,interfaces_bordures)
            
            
            set_route_map(routeur["nom"])

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





repertoire_projet = "C:\\Users\\Gauthier\\GNS3\\projects\\GNS3_project1"
json_file = "C:\\Users\\Gauthier\\Documents\\NAS\\NAS\\data\\data.json"
project_name = os.path.basename(repertoire_projet)

intentions = load_data(json_file)

envoi_telnet = False

if envoi_telnet :
    noeuds = start_telnet(project_name)

logic(intentions)

#drag_and_drop(repertoire_projet)