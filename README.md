# FakeAP v4.0 — Evil Twin & Captive Portal Framework

> Projet educatif demontrant les mecanismes d'une attaque WiFi Evil Twin  
> avec portail captif integre, a des fins de recherche et de formation en cybersecurite.

---

## Table des matieres

- [Presentation](#presentation)
- [Objectifs pedagogiques](#objectifs-pedagogiques)
- [Fonctionnalites](#fonctionnalites)
- [Architecture technique](#architecture-technique)
- [Prerequis](#prerequis)
- [Installation](#installation)
- [Utilisation](#utilisation)
- [Portails captifs disponibles](#portails-captifs-disponibles)
- [Fichiers generes](#fichiers-generes)
- [Avertissement legal](#avertissement-legal)
- [Auteur](#auteur)

---

## Presentation

FakeAP v4.0 est un framework Python complet qui simule une attaque WiFi de type Evil Twin
(Rogue Access Point) couplee a un portail captif dynamique.

Ce projet a ete realise dans un cadre strictement educatif pour illustrer les vulnerabilites
des reseaux WiFi ouverts et les techniques d'attaque Man-in-the-Middle (MITM) etudiees en
securite informatique offensive.

Il s'adresse aux etudiants en cybersecurite, aux pentesters en formation, et a toute personne
souhaitant comprendre concretement ces mecanismes d'attaque afin de mieux s'en defendre.

---

## Objectifs pedagogiques

Ce projet permet de comprendre et d'illustrer les concepts suivants :

- Comment fonctionne une attaque Evil Twin / Rogue AP sur les reseaux 802.11
- Le mecanisme de deauthentification WiFi (attaque de desassociation IEEE 802.11)
- Le fonctionnement d'un portail captif et son interception DNS
- La mise en place d'un Man-in-the-Middle sur une couche reseau locale
- Les vecteurs de phishing WiFi utilises dans des attaques reelles
- La chaine complete : AP frauduleux -> DHCP/DNS Sinkhole -> Portail -> Capture de credentials

---

## Fonctionnalites

Module                  | Description
------------------------|---------------------------------------------------------------
Rogue Access Point      | Creation d'un AP WiFi frauduleux avec hostapd (Open ou WPA2 simule)
Portail captif HTTP     | Serveur HTTP integre avec 18+ templates de pages imitees
DHCP & DNS Sinkhole     | Distribution d'adresses IP + redirection totale du DNS via dnsmasq
Deauth Attack 802.11    | Desauthentification des clients via aireplay-ng (cible unique ou continue)
Scan de reseaux         | Detection des AP environnants pour cloner un reseau existant
Dual Interface          | Support de 2 cartes WiFi simultanees (AP + Deauth separes)
Multi-langues           | Portails traduits en Francais, Anglais, Espagnol, Portugais
SSID Spoofing           | Generation de SSID imitant les operateurs reels (SFR, Orange, Free, MTN...)
Capture de donnees      | Enregistrement JSON + CSV des credentials soumis via les formulaires
Filtrage & Securite     | Whitelist MAC, blocage IP automatique, limite de tentatives configurables
Stealth Mode            | Mode discret avec reduction des logs visibles dans le terminal
Watchdog                | Surveillance et redemarrage automatique des services critiques
Dashboard live          | Interface terminal temps reel : connexions, captures, requetes HTTP
UX Hacker Cinema        | Animations Matrix, glitch, typewriter, hex dump dans le terminal

---

## Architecture technique

```
FakeAP v4.0
|
|-- setup_network()           -> Configuration IP / iw / mode AP sur l'interface
|
|-- hostapd                   -> Creation du point d'acces WiFi (ssid, channel, auth)
|
|-- dnsmasq                   -> DHCP + DNS Sinkhole
|   `-- address=/#/192.168.10.1  -> Redirige TOUS les domaines vers le gateway local
|
|-- HTTPServer :80             -> Portail captif (PortalHandler)
|   |-- Templates inline       -> Google, Netflix, Banque, Hotel, Operateur
|   `-- Templates fichiers     -> Facebook, TikTok, Instagram, WhatsApp, Orange...
|
|-- Deauth Engine              -> aireplay-ng -0 (tir unique / boucle continue)
|
|-- Capture Engine             -> captures.json + captures.csv
|   `-- Horodatage, IP, MAC, User-Agent, champs formulaire
|
`-- Live Dashboard             -> Stats temps reel via threading
```

---

## Prerequis

**Systeme d'exploitation :** Linux — Kali Linux ou Parrot OS recommande

**Materiel :** Une carte WiFi compatible mode Monitor + AP est indispensable.

Cartes recommandees : Alfa AWUS036ACH · Alfa AWUS036NHA · TP-Link TL-WN722N v1

**Dependances systeme :**

```bash
sudo apt update && sudo apt install -y hostapd dnsmasq aircrack-ng iw net-tools
```

**Python :** 3.8 ou superieur — aucune dependance externe pip, uniquement la bibliotheque standard.

---

## Installation

```bash
# 1. Cloner le depot
git clone https://github.com/exploit4040/FakeAP.git
cd FakeAP

# 2. Donner les permissions d'execution
chmod +x fakeAP4_1.py

# 3. Lancer avec les privileges root (obligatoire)
sudo python3 fakeAP4_1.py
```

Les privileges root sont obligatoires pour manipuler les interfaces reseau,
configurer iptables et demarrer hostapd / dnsmasq.

---

## Utilisation

Au lancement, FakeAP v4.0 presente un menu interactif permettant de :

1. Choisir un template de portail captif parmi les 18 disponibles
2. Configurer le SSID (manuel, clone d'un reseau scanne, ou aleatoire par operateur)
3. Selectionner l'interface WiFi (detection automatique mono/dual carte)
4. Parametrer le mode AP : Open ou WPA2 simule
5. Activer les options avancees : Stealth Mode, Watchdog, Deauth continu

Une fois demarre, le dashboard terminal affiche en temps reel :

```
  FakeAP v4.0 ACTIF

  SSID         :  Facebook_Free_WiFi
  PAGE         :  Facebook WiFi
  INTERFACE AP :  wlp2s0
  GATEWAY      :  192.168.10.1/24
  CANAL        :  6
  MODE AP      :  OPEN
  STEALTH      :  OFF
  WATCHDOG     :  ON
  CAPTURES     :  captures.json  +  captures.csv
  LOG HTTP     :  http_requests.log

  En attente de connexions...   Ctrl+C pour arreter
```

---

## Portails captifs disponibles

```
 N    Nom                  SSID par defaut
------------------------------------------------------
  1   Facebook WiFi        Facebook_Free_WiFi
  2   TikTok Hotspot       TikTok_Free_WiFi
  3   Airtel Free WiFi     Airtel_Free_WiFi
  4   Instagram Zone       Instagram_WiFi
  5   Windows Update       Windows_Update
  6   WhatsApp Connect     WhatsApp_WiFi
  7   Telegram Access      Telegram_WiFi
  8   CanalBox WiFi        CanalBox_WiFi
  9   Orange Freebox       Orange_Free_WiFi
 10   Vodacom Network      Vodacom_WiFi
 13   WiFiToo Clone        WiFiToo_Free
 14   Google Account       Google_Starbucks
 15   Netflix Portal       Netflix_WiFi
 16   Banque en ligne      BNP_Free_WiFi
 17   Hotel WiFi           Hotel_Premium_WiFi
 18   Operateur Mobile     Orange_4G_WiFi
```

---

## Fichiers generes

Fichier              | Contenu
---------------------|----------------------------------------------------------------
captures.json        | Credentials captures avec horodatage, IP, User-Agent et champs
captures.csv         | Memes donnees au format tableur (compatible Excel / LibreOffice)
http_requests.log    | Journal complet de toutes les requetes HTTP recues par le portail

---

## Avertissement legal

Ce projet est developpe et partage dans un but exclusivement educatif et pedagogique.

Son utilisation est strictement reservee a des environnements que vous possedez ou pour
lesquels vous disposez d'une autorisation ecrite et explicite du proprietaire du reseau.

Toute utilisation sur un reseau ou un systeme tiers sans autorisation prealable est illegale
dans la quasi-totalite des pays et peut entrainer de lourdes sanctions penales.

L'auteur decline toute responsabilite pour toute utilisation abusive, illegale
ou malveillante de cet outil.

---

## Auteur

ML — Etudiant & Chercheur en Securite Informatique

GitHub : https://github.com/exploit4040

---

"Understanding how attacks work is the first step toward building stronger defenses."
