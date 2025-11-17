#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script pour lire les capteurs Xiaomi via les publicités BLE (advertisements)
Méthode passive qui n'établit pas de connexion
Fonctionne pour tous les capteurs, notamment Hardware 0159
"""

import sys
from bluepy import btle
import struct
import time
from datetime import datetime

class XiaomiAdvertisementScanner(btle.DefaultDelegate):
    """Scanner de publicités BLE pour capteurs Xiaomi"""
    
    def __init__(self, target_macs=None):
        btle.DefaultDelegate.__init__(self)
        self.target_macs = [mac.upper() for mac in target_macs] if target_macs else []
        self.devices_data = {}
        
    def handleDiscovery(self, dev, isNewDev, isNewData):
        """Appelé pour chaque appareil découvert ou mis à jour"""
        
        # Filtrer uniquement nos capteurs
        if self.target_macs and dev.addr.upper() not in self.target_macs:
            return
            
        # Chercher les données dans les publicités
        for (adtype, desc, value) in dev.getScanData():
            # Service Data - UUID 0x181a (ATC/pvvx format)
            if adtype == 22 and value.startswith('1a18'):
                print(f"\n🔍 Format ATC/pvvx détecté pour {dev.addr.upper()}: {value}")
                try:
                    self.parse_atc_format(dev.addr.upper(), value, dev.rssi)
                except Exception as e:
                    print(f"  ✗ Erreur parsing ATC: {e}")
                    import traceback
                    traceback.print_exc()
                    
            # Service Data - UUID 0xfe95 (Xiaomi stock)
            elif adtype == 22 and value.startswith('95fe'):
                print(f"\n🔍 Format Xiaomi stock détecté pour {dev.addr.upper()}: {value}")
                try:
                    self.parse_xiaomi_mibeacon(dev.addr.upper(), value, dev.rssi)
                except Exception as e:
                    print(f"  ✗ Erreur parsing Xiaomi: {e}")
                    import traceback
                    traceback.print_exc()
                    
            # Service Data - UUID 0xfcd2 (pvvx custom format)
            elif adtype == 22 and value.startswith('d2fc'):
                print(f"\n🔍 Format pvvx custom détecté pour {dev.addr.upper()}: {value}")
                try:
                    self.parse_pvvx_format(dev.addr.upper(), value, dev.rssi)
                except Exception as e:
                    print(f"  ✗ Erreur parsing pvvx: {e}")
                    import traceback
                    traceback.print_exc()
    
    def parse_pvvx_format(self, mac, data, rssi):
        """
        Parse le format pvvx custom (UUID 0xfcd2)
        Format non documenté - analysons toutes les possibilités
        Valeurs attendues : ~23°C et ~52%
        """
        try:
            bytes_data = bytes.fromhex(data)
            payload = bytes_data[2:]  # Ignorer UUID d2fc
            
            print(f"  Payload ({len(payload)} octets): {' '.join([f'{b:02x}' for b in payload])}")
            print(f"  Cherche: 23°C (2300 = 0x08FC) et 52% (52 = 0x34, 520 = 0x0208)")
            print()
            
            # Tester toutes les positions pour température (~23°C)
            print("  🌡️  Tests TEMPÉRATURE (cherche ~23°C):")
            for pos in range(0, len(payload)-1):
                # Little endian
                val_le = struct.unpack('<H', payload[pos:pos+2])[0]
                if 1500 <= val_le <= 3000:  # Recherche 2300 ±700
                    print(f"     pos {pos}-{pos+1} LE: {val_le} → {val_le/100:.2f}°C")
                
                # Big endian
                val_be = struct.unpack('>H', payload[pos:pos+2])[0]
                if 1500 <= val_be <= 3000:
                    print(f"     pos {pos}-{pos+1} BE: {val_be} → {val_be/100:.2f}°C")
                    
                # Signed little endian
                val_sle = struct.unpack('<h', payload[pos:pos+2])[0]
                if 150 <= val_sle <= 300:  # Recherche 230 ±70
                    print(f"     pos {pos}-{pos+1} sLE÷10: {val_sle} → {val_sle/10:.1f}°C")
                    
                # Signed big endian
                val_sbe = struct.unpack('>h', payload[pos:pos+2])[0]
                if 150 <= val_sbe <= 300:
                    print(f"     pos {pos}-{pos+1} sBE÷10: {val_sbe} → {val_sbe/10:.1f}°C")
            
            # Tester pour humidité (~52%)
            print("\n  💧 Tests HUMIDITÉ (cherche ~52%):")
            for pos in range(len(payload)):
                val_byte = payload[pos]
                if 40 <= val_byte <= 70:
                    print(f"     pos {pos} (1 octet): {val_byte}%")
                    
            for pos in range(0, len(payload)-1):
                val_le = struct.unpack('<H', payload[pos:pos+2])[0]
                if 400 <= val_le <= 700:
                    print(f"     pos {pos}-{pos+1} LE÷10: {val_le} → {val_le/10:.1f}%")
                    
                val_be = struct.unpack('>H', payload[pos:pos+2])[0]
                if 400 <= val_be <= 700:
                    print(f"     pos {pos}-{pos+1} BE÷10: {val_be} → {val_be/10:.1f}%")
                    
        except Exception as e:
            print(f"  ✗ Erreur: {e}")
    
    def parse_atc_format(self, mac, data, rssi):
        """
        Parse le format ATC (UUID 0x181a)
        Format: 1a18 + MAC(6) + Temperature(2) + Humidity(1) + Battery(1) + Battery_mV(2) + Counter(1)
        """
        try:
            bytes_data = bytes.fromhex(data)
            
            if len(bytes_data) < 13:  # UUID(2) + données(11)
                print(f"  ✗ Payload trop court: {len(bytes_data)} octets")
                return
            
            # Ignorer UUID (2 octets: 1a18)
            payload = bytes_data[2:]
            
            # MAC Address (6 octets) - big endian
            mac_bytes = payload[0:6]
            
            # Temperature (2 octets) - signed int16, big endian, en dixièmes de degré
            temp_raw = struct.unpack('>h', payload[6:8])[0]
            temperature = temp_raw / 10.0
            
            # Humidity (1 octet) - en %
            humidity = payload[8]
            
            # Battery % (1 octet)
            battery_pct = payload[9]
            
            # Battery mV (2 octets) - unsigned int16, big endian
            battery_mv = struct.unpack('>H', payload[10:12])[0]
            
            # Counter (1 octet)
            counter = payload[12] if len(payload) > 12 else 0
            
            # Affichage
            print(f"  📊 {mac}")
            print(f"     🌡️  Température: {temperature:.1f}°C")
            print(f"     💧 Humidité: {humidity}%")
            print(f"     🔋 Batterie: {battery_pct}% ({battery_mv} mV)")
            print(f"     📡 RSSI: {rssi} dBm")
            print(f"     🔢 Counter: {counter}")
            
            # Stockage
            self.devices_data[mac] = {
                'temperature': temperature,
                'humidity': humidity,
                'battery': battery_pct,
                'battery_mv': battery_mv,
                'rssi': rssi,
                'timestamp': datetime.now()
            }
            
        except Exception as e:
            print(f"  ✗ Erreur parsing ATC: {e}")
            import traceback
            traceback.print_exc()
    
    def parse_xiaomi_mibeacon(self, mac, data, rssi):
        """
        Parse les données Xiaomi MiBeacon (UUID 0xfe95)
        Format: 95fe + frame_control(2) + product_id(2) + frame_counter(1) + MAC(6) + capability(1) + [objects]
        """
        try:
            # Convertir hex string en bytes
            bytes_data = bytes.fromhex(data)
            
            if len(bytes_data) < 5:
                return
            
            # Debug: afficher la structure
            print(f"\n  DEBUG {mac}:")
            print(f"    Données brutes: {data}")
            print(f"    Longueur: {len(bytes_data)} octets")
            
            # Ignorer UUID (2 octets: 95fe -> fe95)
            payload = bytes_data[2:]
            print(f"    Payload: {payload.hex()}")
            
            if len(payload) < 11:
                print(f"    Payload trop court")
                return
            
            # Frame Control (2 octets)
            frame_control = struct.unpack('<H', payload[0:2])[0]
            print(f"    Frame Control: 0x{frame_control:04x}")
            
            # Product ID (2 octets)
            product_id = struct.unpack('<H', payload[2:4])[0]
            print(f"    Product ID: 0x{product_id:04x}")
            
            # Frame Counter (1 octet)
            frame_cnt = payload[4]
            print(f"    Frame Counter: {frame_cnt}")
            
            # MAC Address (6 octets) - en little endian
            mac_bytes = payload[5:11]
            mac_str = ':'.join([f'{b:02x}' for b in reversed(mac_bytes)]).upper()
            print(f"    MAC: {mac_str}")
            
            # Position actuelle dans les données
            pos = 11
            
            # Si présent: Capability (1 octet)
            has_capability = frame_control & 0x0020
            has_object = frame_control & 0x0040
            has_mesh = frame_control & 0x0080
            has_encryption = frame_control & 0x0008
            has_mac = frame_control & 0x0010
            
            print(f"    Capability bit: {bool(has_capability)}")
            print(f"    Object bit: {bool(has_object)}")
            print(f"    MAC bit: {bool(has_mac)}")
            
            if has_capability and len(payload) > pos:
                capability = payload[pos]
                print(f"    Capability: 0x{capability:02x}")
                pos += 1
            
            # Lire les objets (Type-Length-Value)
            temperature = None
            humidity = None
            battery = None
            
            print(f"    Position objets: {pos}, reste: {len(payload) - pos} octets")
            print(f"    Données objets: {payload[pos:].hex()}")
            
            while pos < len(payload):
                if pos + 3 > len(payload):
                    break
                    
                obj_type = payload[pos]
                obj_length = payload[pos + 1]
                
                print(f"      Type: 0x{obj_type:02x}, Length: {obj_length}")
                
                if pos + 2 + obj_length > len(payload):
                    break
                
                obj_data = payload[pos + 2:pos + 2 + obj_length]
                print(f"      Data: {obj_data.hex()}")
                
                # Type 0x04 = Temperature (2 octets, signed, div 10)
                if obj_type == 0x04 and obj_length == 2:
                    temperature = struct.unpack('<h', obj_data)[0] / 10.0
                    print(f"      → Température: {temperature}°C")
                
                # Type 0x06 = Humidity (2 octets, unsigned, div 10)
                elif obj_type == 0x06 and obj_length == 2:
                    humidity = struct.unpack('<H', obj_data)[0] / 10.0
                    print(f"      → Humidité: {humidity}%")
                
                # Type 0x0A = Battery (1 octet)
                elif obj_type == 0x0a and obj_length == 1:
                    battery = obj_data[0]
                    print(f"      → Batterie: {battery}%")
                
                # Type 0x0D = Temperature + Humidity (4 octets)
                elif obj_type == 0x0d and obj_length == 4:
                    temperature = struct.unpack('<h', obj_data[0:2])[0] / 10.0
                    humidity = struct.unpack('<H', obj_data[2:4])[0] / 10.0
                    print(f"      → Temp+Hum: {temperature}°C, {humidity}%")
                
                pos += 2 + obj_length
            
            # Enregistrer les données si valides
            if temperature is not None and humidity is not None:
                print(f"    ✓ DONNÉES VALIDES TROUVÉES")
                self.devices_data[mac] = {
                    'temperature': temperature,
                    'humidity': humidity,
                    'battery': battery,
                    'rssi': rssi,
                    'timestamp': datetime.now()
                }
            else:
                print(f"    ✗ Pas de données temp/hum")
            
        except Exception as e:
            print(f"    ✗ Erreur: {e}")
            import traceback
            traceback.print_exc()
    
    def parse_xiaomi_service_data(self, mac, data):
        """Parse les données de service Xiaomi"""
        # Format: UUID(4) + Data
        if len(data) < 10:
            return
            
        # Extraire les octets (données en hex string)
        try:
            bytes_data = bytes.fromhex(data[4:])  # Ignorer UUID (4 chars)
            
            if len(bytes_data) >= 13:
                # Format Xiaomi MiBeacon
                # Rechercher le type de données 0x0D (Temperature & Humidity)
                i = 0
                while i < len(bytes_data) - 3:
                    obj_id = struct.unpack('<H', bytes_data[i:i+2])[0]
                    
                    if obj_id == 0x0D04:  # Temperature & Humidity
                        if i + 6 <= len(bytes_data):
                            temp_raw = struct.unpack('<h', bytes_data[i+2:i+4])[0]
                            hum_raw = struct.unpack('<H', bytes_data[i+4:i+6])[0]
                            
                            temperature = temp_raw / 10.0
                            humidity = hum_raw / 10.0
                            
                            self.devices_data[mac] = {
                                'temperature': temperature,
                                'humidity': humidity,
                                'battery': None,
                                'timestamp': datetime.now()
                            }
                            return
                    
                    i += 1
        except:
            pass


def scan_advertisements(mac_addresses, duration=30, debug=False):
    """
    Scanner les publicités BLE des capteurs
    
    Args:
        mac_addresses: Liste des adresses MAC à surveiller
        duration: Durée du scan en secondes
        debug: Mode debug
    """
    print("="*70)
    print("  Scan des publicités BLE des capteurs Xiaomi")
    print("="*70)
    print(f"\n🔍 Écoute des publicités pendant {duration} secondes...")
    print(f"📱 Capteurs surveillés: {len(mac_addresses)}")
    for mac in mac_addresses:
        print(f"   - {mac}")
    print()
    
    scanner = btle.Scanner()
    # Enlever le filtre pour voir TOUS les appareils
    delegate = XiaomiAdvertisementScanner([])  # Liste vide = pas de filtre
    scanner.withDelegate(delegate)
    
    try:
        # Scanner pendant la durée spécifiée - SANS delegate pour commencer
        print("⏳ Scan en cours...")
        devices = scanner.scan(duration, passive=False)
        
        print(f"\n✓ Scan terminé")
        print(f"📊 Appareils détectés: {len(devices)}\n")
        
        # Traiter manuellement les devices après le scan
        target_macs_upper = [m.upper() for m in mac_addresses]
        
        for dev in devices:
            # Récupérer le nom
            name = ""
            for (adtype, desc, value) in dev.getScanData():
                if desc == "Complete Local Name" or desc == "Short Local Name":
                    name = value
            
            # Afficher tous les appareils ATC ou LYWSD
            if "ATC" in name or "LYWSD" in name:
                print(f"\n{'='*60}")
                print(f"📱 Appareil: {dev.addr.upper()}")
                print(f"   Nom: {name}")
                print(f"   RSSI: {dev.rssi} dBm")
                print("-"*60)
                
                # Traiter les données
                for (adtype, desc, value) in dev.getScanData():
                    print(f"   [{adtype:2d}] {desc:30s}: {value}")
                    
                    # Parser selon le type
                    if adtype == 22:  # Service Data
                        if value.startswith('d2fc'):
                            print(f"\n   🔍 Format pvvx détecté !")
                            delegate.parse_pvvx_format(dev.addr.upper(), value, dev.rssi)
                        elif value.startswith('1a18'):
                            print(f"\n   🔍 Format ATC détecté !")
                            delegate.parse_atc_format(dev.addr.upper(), value, dev.rssi)
                        elif value.startswith('95fe'):
                            print(f"\n   🔍 Format Xiaomi stock détecté !")
                            delegate.parse_xiaomi_mibeacon(dev.addr.upper(), value, dev.rssi)
                
                print("="*60)
        
        # Afficher les données récupérées
        if delegate.devices_data:
            print("="*70)
            print("  DONNÉES RÉCUPÉRÉES")
            print("="*70)
            
            for mac, data in delegate.devices_data.items():
                print(f"\n{'='*50}")
                print(f"Capteur: {mac}")
                print(f"Date/Heure: {data['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"Signal: {data.get('rssi', 'N/A')} dBm")
                print("-"*50)
                print(f"🌡️  Température: {data['temperature']:.1f}°C")
                print(f"💧 Humidité: {data['humidity']:.1f}%")
                if data['battery'] is not None:
                    print(f"🔋 Batterie: {data['battery']}%")
                if 'battery_mv' in data:
                    print(f"⚡ Voltage: {data['battery_mv']} mV")
                print("="*50)
        else:
            print("⚠️  Aucune donnée de température/humidité trouvée dans les publicités")
            print("\nℹ️  Informations de debug:")
            
            # Afficher toutes les données reçues pour debug
            target_macs_upper = [m.upper() for m in mac_addresses]
            for dev in devices:
                # Afficher tous les appareils qui ressemblent à des capteurs
                name = ""
                for (adtype, desc, value) in dev.getScanData():
                    if desc == "Complete Local Name" or desc == "Short Local Name":
                        name = value
                
                # Afficher si c'est un de nos capteurs OU s'il contient ATC/LYWSD
                if dev.addr.upper() in target_macs_upper or "ATC" in name or "LYWSD" in name:
                    print(f"\n  Appareil: {dev.addr.upper()} - {name} (RSSI: {dev.rssi} dBm)")
                    for (adtype, desc, value) in dev.getScanData():
                        print(f"    [{adtype}] {desc}: {value}")
        
        return delegate.devices_data
        
    except btle.BTLEException as e:
        print(f"✗ Erreur lors du scan: {e}")
        return {}


def main():
    """Fonction principale"""
    
    print("="*70)
    print("  Lecture des capteurs Xiaomi via publicités BLE")
    print("  Méthode passive - pas de connexion nécessaire")
    print("="*70)
    
    # Capteurs à surveiller
    sensors = [
        "A4:C1:38:84:F0:8C", # Capteur 101 => Flashé le 16/11/2025 => OK
        "A4:C1:38:EF:03:BD", # Capteur 102 => Flashé le 17/11/2025 => OK
        "A4:C1:38:9D:9E:0D", # Capteur 103 => Flashé le 17/11/2025 => OK
        "A4:C1:38:CB:F1:95", # Capteur 104 => Flashé le 17/11/2025 => OK
        "A4:C1:38:1E:9C:7F", # Capteur 105 => Flashé le 17/11/2025 => OK

        # "A4:C1:38:24:E3:4D",  # Capteur 106 => Reste à faire
    ]
    
    # Scanner les publicités
    data = scan_advertisements(sensors, duration=30, debug=True)
    
    if not data:
        print("\n💡 CONSEIL:")
        print("   Les capteurs avec firmware stock Xiaomi n'émettent pas toujours")
        print("   de données dans leurs publicités BLE.")
        print("\n   Solution recommandée: Flasher le firmware custom 'pvvx'")
        print("   qui émet les données en continu dans les publicités.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interruption par l'utilisateur")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Erreur: {e}")
        sys.exit(1)
