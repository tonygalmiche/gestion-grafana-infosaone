#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script pour récupérer les données des capteurs Xiaomi Mijia LYWSD03MMC
Température, humidité et niveau de batterie
"""

import sys
from bluepy import btle
import struct
import time
from datetime import datetime

class XiaomiMijiaLYWSD03MMC:
    """
    Classe pour lire les données des capteurs Xiaomi Mijia LYWSD03MMC
    Support firmware stock et custom (pvvx/ATC)
    """
    
    # Handles possibles pour les caractéristiques du capteur (selon firmware)
    TEMP_HUM_HANDLES = [0x36, 0x003a, 0x0038, 0x002d, 0x004c]  # Handles pour température et humidité
    BATTERY_HANDLES = [0x18, 0x001b, 0x0019, 0x001a]  # Handles pour la batterie
    
    # UUID pour le firmware custom pvvx
    PVVX_UUID = "0000181a-0000-1000-8000-00805f9b34fb"
    
    def __init__(self, mac_address):
        """
        Initialisation avec l'adresse MAC du capteur
        
        Args:
            mac_address: Adresse MAC du capteur (format: AA:BB:CC:DD:EE:FF)
        """
        self.mac_address = mac_address.upper()
        self.peripheral = None
        self.notification_data = None
        self.hardware_version = None
        
    def connect(self, max_retries=5, retry_delay=3):
        """
        Connexion au capteur avec retentatives
        
        Args:
            max_retries: Nombre maximum de tentatives
            retry_delay: Délai entre les tentatives en secondes
        """
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    print(f"  Tentative {attempt + 1}/{max_retries}...")
                    time.sleep(retry_delay)
                else:
                    print(f"Connexion au capteur {self.mac_address}...")
                
                # Essayer d'abord avec addrType public
                try:
                    self.peripheral = btle.Peripheral(self.mac_address, addrType=btle.ADDR_TYPE_PUBLIC)
                except:
                    # Si échec, essayer avec addrType random
                    print("  Essai avec addrType random...")
                    self.peripheral = btle.Peripheral(self.mac_address, addrType=btle.ADDR_TYPE_RANDOM)
                    
                time.sleep(0.5)  # Petite pause après connexion
                print("✓ Connecté")
                return True
                
            except btle.BTLEException as e:
                if attempt == max_retries - 1:
                    print(f"✗ Erreur de connexion après {max_retries} tentatives: {e}")
                    return False
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"✗ Erreur: {e}")
                    return False
        return False
            
    def disconnect(self):
        """
        Déconnexion du capteur
        """
        if self.peripheral:
            try:
                self.peripheral.disconnect()
                time.sleep(1)  # Pause après déconnexion
                print("Déconnecté")
            except:
                pass
    
    def get_device_info(self):
        """
        Récupère les informations du capteur (firmware, modèle, etc.)
        
        Returns:
            dict: Informations du capteur
        """
        if not self.peripheral:
            return None
            
        info = {
            'firmware': None,
            'hardware': None,
            'software': None,
            'manufacturer': None,
            'model': None
        }
        
        try:
            # Handle 0x0014: Firmware Revision
            try:
                data = self.peripheral.readCharacteristic(0x0014)
                info['firmware'] = data.decode('utf-8').strip()
            except:
                pass
                
            # Handle 0x0016: Hardware Revision
            try:
                data = self.peripheral.readCharacteristic(0x0016)
                info['hardware'] = data.decode('utf-8').strip()
                self.hardware_version = info['hardware']  # Stocker pour usage ultérieur
            except:
                pass
                
            # Handle 0x0012: Software Revision
            try:
                data = self.peripheral.readCharacteristic(0x0012)
                info['software'] = data.decode('utf-8').strip()
            except:
                pass
                
            # Handle 0x000e: Manufacturer Name
            try:
                data = self.peripheral.readCharacteristic(0x000e)
                info['manufacturer'] = data.decode('utf-8').strip()
            except:
                pass
                
            # Handle 0x0010: Model Number
            try:
                data = self.peripheral.readCharacteristic(0x0010)
                info['model'] = data.decode('utf-8').strip()
            except:
                pass
                
        except Exception as e:
            pass
            
        return info
                
    def read_data(self, debug=False):
        """
        Lecture des données du capteur
        
        Args:
            debug: Afficher les données brutes pour débogage
            
        Returns:
            dict: Dictionnaire contenant température, humidité et batterie
        """
        if not self.peripheral:
            print("Erreur: Pas de connexion établie")
            return None
            
        temperature = None
        humidity = None
        battery = None
        
        # Pour les capteurs Hardware 0159, essayer de déclencher une mise à jour
        if self.hardware_version and '0159' in self.hardware_version:
            if debug:
                print("  Détection Hardware 0159 - Tentative de rafraîchissement des données...")
            try:
                # Essayer d'écrire sur le handle de contrôle pour déclencher une lecture
                # Handle 0x0046 ou 0x0033 selon les firmware
                for ctrl_handle in [0x0046, 0x0033, 0x004b]:
                    try:
                        self.peripheral.writeCharacteristic(ctrl_handle, b'\x01\x00', withResponse=False)
                        time.sleep(1)
                        if debug:
                            print(f"  Écriture sur handle 0x{ctrl_handle:04x} réussie")
                        break
                    except:
                        continue
            except Exception as e:
                if debug:
                    print(f"  Échec rafraîchissement: {e}")
        
        # Essayer d'activer les notifications pour réveiller le capteur
        try:
            # Handle de notification 0x0038 (notification descriptor)
            self.peripheral.writeCharacteristic(0x0038, b'\x01\x00', withResponse=True)
            time.sleep(0.5)
        except:
            pass
        
        # Essayer différents handles pour température et humidité
        for handle in self.TEMP_HUM_HANDLES:
            try:
                data = self.peripheral.readCharacteristic(handle)
                
                if debug:
                    hex_data = ' '.join([f'{b:02x}' for b in data])
                    print(f"  Handle 0x{handle:04x}: {len(data)} octets -> {hex_data}")
                
                if len(data) < 2:
                    continue
                
                # Décodage de la température (2 premiers octets)
                temp_raw = struct.unpack('<H', data[:2])[0]
                temp_value = temp_raw / 100.0
                
                # Vérification de cohérence de la température (-40 à +80°C)
                if -40 <= temp_value <= 80:
                    temperature = temp_value
                else:
                    continue
                
                # Décodage de l'humidité si disponible
                if len(data) >= 3:
                    hum_value = struct.unpack('B', data[2:3])[0]
                    if 0 <= hum_value <= 100:
                        humidity = hum_value
                elif len(data) >= 4:
                    # Essayer le format 2 octets pour l'humidité
                    hum_raw = struct.unpack('<H', data[2:4])[0]
                    hum_value = hum_raw / 100.0
                    if 0 <= hum_value <= 100:
                        humidity = hum_value
                
                # Si on a réussi à lire une température cohérente, on sort
                if temperature is not None:
                    if debug:
                        print(f"  ✓ Données valides trouvées sur handle 0x{handle:04x}")
                    break
                    
            except Exception as e:
                if debug:
                    print(f"  Erreur sur handle 0x{handle:04x}: {e}")
                continue
        
        # Si aucune température n'a été lue
        if temperature is None:
            print("✗ Impossible de lire les données de température/humidité")
            print("  ℹ️  Pour les capteurs Hardware 0159, essayez d'appuyer sur le bouton avant la lecture")
            return None
        
        # Essayer différents handles pour la batterie
        for handle in self.BATTERY_HANDLES:
            try:
                battery_data = self.peripheral.readCharacteristic(handle)
                if len(battery_data) >= 1:
                    bat_value = struct.unpack('B', battery_data[:1])[0]
                    if 0 <= bat_value <= 100:
                        battery = bat_value
                        break
            except:
                continue
                
        return {
            'temperature': temperature,
            'humidity': humidity,
            'battery': battery,
            'timestamp': datetime.now()
        }
            
    def display_data(self, data, device_info=None):
        """
        Affichage formaté des données
        
        Args:
            data: Dictionnaire des données du capteur
            device_info: Informations sur le capteur (firmware, etc.)
        """
        if not data:
            return
            
        print("\n" + "="*50)
        print(f"Capteur: {self.mac_address}")
        
        # Affichage des infos du capteur si disponibles
        if device_info:
            if device_info['manufacturer']:
                print(f"Fabricant: {device_info['manufacturer']}")
            if device_info['model']:
                print(f"Modèle: {device_info['model']}")
            if device_info['firmware']:
                print(f"Firmware: {device_info['firmware']}")
            if device_info['hardware']:
                print(f"Hardware: {device_info['hardware']}")
            if device_info['software']:
                print(f"Software: {device_info['software']}")
                
        print(f"Date/Heure: {data['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
        print("-"*50)
        print(f"🌡️  Température: {data['temperature']:.1f}°C")
        if data['humidity'] is not None:
            print(f"💧 Humidité: {data['humidity']:.0f}%")
        else:
            print(f"💧 Humidité: Non disponible")
        if data['battery'] is not None:
            print(f"🔋 Batterie: {data['battery']}%")
        print("="*50)


def scan_devices(duration=10):
    """
    Scanner les appareils Bluetooth à proximité
    
    Args:
        duration: Durée du scan en secondes
    """
    print(f"\nRecherche d'appareils Bluetooth pendant {duration} secondes...")
    scanner = btle.Scanner()
    
    try:
        devices = scanner.scan(duration)
        xiaomi_devices = []
        
        print(f"\nAppareils trouvés: {len(devices)}")
        print("-"*70)
        
        for dev in devices:
            # Recherche des capteurs Xiaomi
            name = ""
            for (adtype, desc, value) in dev.getScanData():
                if desc == "Complete Local Name" or desc == "Short Local Name":
                    name = value
                    
            # Affichage de tous les appareils
            print(f"Adresse: {dev.addr.upper():<20} RSSI: {dev.rssi:>4} dBm  Nom: {name}")
            
            # Identification des capteurs Xiaomi Mijia
            if "LYWSD03MMC" in name or "MJ_HT_V1" in name:
                xiaomi_devices.append(dev.addr.upper())
                
        if xiaomi_devices:
            print("\n📱 Capteurs Xiaomi Mijia détectés:")
            for addr in xiaomi_devices:
                print(f"  - {addr}")
        else:
            print("\n⚠️  Aucun capteur Xiaomi Mijia LYWSD03MMC détecté")
            
        return xiaomi_devices
        
    except btle.BTLEException as e:
        print(f"Erreur lors du scan: {e}")
        return []


def main():
    """
    Fonction principale
    """
    print("="*70)
    print("  Lecture des capteurs Xiaomi Mijia LYWSD03MMC")
    print("="*70)
    
    # Mode debug pour voir les données brutes
    import sys
    debug_mode = '--debug' in sys.argv or '-d' in sys.argv
    
    if debug_mode:
        print("\n🔍 MODE DEBUG ACTIVÉ\n")
    
    # Liste des adresses MAC de vos capteurs
    # Modifiez cette liste avec les adresses de vos capteurs
    sensors = [
        "A4:C1:38:84:F0:8C",  # Capteur 101 (celui-ci fonctionne) => Mise à jour firmware OK => Ne fonctionne plus après cette mise à jour

        # "A4:C1:38:1E:9C:7F",  # Capteur 5 (celui-ci ne fonctionne pas bien)
        # "A4:C1:38:24:E3:4D",  # Capteur 2
        # "A4:C1:38:CB:F1:95",  # Capteur 3
        # "A4:C1:38:EF:03:BD",  # Capteur 4
        # "A4:C1:38:9D:9E:0D",  # Capteur 6

    ]
    

#Adresse: A4:C1:38:84:F0:8C    RSSI:  -49 dBm  Nom: LYWSD03MMC


    # Si aucun capteur n'est configuré, lancer un scan
    if not sensors:
        print("\n⚠️  Aucun capteur configuré dans la liste 'sensors'")
        response = input("\nVoulez-vous scanner les appareils Bluetooth ? (o/n): ")
        
        if response.lower() == 'o':
            found_sensors = scan_devices(10)
            if found_sensors:
                print("\nVeuillez ajouter ces adresses dans le script.")
            return
        else:
            print("\nAjoutez les adresses MAC de vos capteurs dans la liste 'sensors'")
            print("Format: A4:C1:38:XX:XX:XX")
            return
    
    # Lecture des données de chaque capteur
    for i, mac_address in enumerate(sensors, 1):
        print(f"\n[{i}/{len(sensors)}]")
        sensor = XiaomiMijiaLYWSD03MMC(mac_address)
        
        if sensor.connect():
            # Lire les infos du capteur
            device_info = sensor.get_device_info()
            
            # Lire les données
            data = sensor.read_data(debug=debug_mode)
            if data:
                sensor.display_data(data, device_info)
            sensor.disconnect()
            
        # Pause plus longue entre chaque capteur pour laisser le temps au Bluetooth
        if mac_address != sensors[-1]:
            print(f"\n⏳ Pause de 5 secondes avant le prochain capteur...")
            time.sleep(5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interruption par l'utilisateur")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Erreur: {e}")
        sys.exit(1)
