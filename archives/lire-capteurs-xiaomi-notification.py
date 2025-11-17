#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script pour lire les capteurs Xiaomi via notifications BLE
Pour les capteurs Hardware 0159 qui nécessitent une interaction physique
"""

import sys
from bluepy import btle
import struct
import time
from datetime import datetime

class NotificationDelegate(btle.DefaultDelegate):
    """Gestionnaire de notifications BLE"""
    
    def __init__(self):
        btle.DefaultDelegate.__init__(self)
        self.data = None
        
    def handleNotification(self, cHandle, data):
        """Appelé lorsqu'une notification est reçue"""
        print(f"  📨 Notification reçue sur handle 0x{cHandle:04x}")
        hex_data = ' '.join([f'{b:02x}' for b in data])
        print(f"      Données: {hex_data} ({len(data)} octets)")
        self.data = (cHandle, data)


def read_with_notification(mac_address, timeout=30):
    """
    Lecture des données via notifications
    Appuyez sur le bouton du capteur pendant la lecture
    
    Args:
        mac_address: Adresse MAC du capteur
        timeout: Délai d'attente en secondes
    """
    print(f"\n{'='*70}")
    print(f"Capteur: {mac_address}")
    print(f"{'='*70}")
    print(f"⏳ En attente de notification pendant {timeout} secondes...")
    print(f"👆 APPUYEZ SUR LE BOUTON DU CAPTEUR MAINTENANT !")
    print(f"{'='*70}\n")
    
    try:
        # Connexion
        peripheral = btle.Peripheral(mac_address)
        peripheral.setDelegate(NotificationDelegate())
        
        # Activer les notifications sur différents handles
        notification_handles = [0x0038, 0x003c, 0x004e]
        
        for handle in notification_handles:
            try:
                peripheral.writeCharacteristic(handle, b'\x01\x00', withResponse=True)
                print(f"✓ Notifications activées sur handle 0x{handle:04x}")
            except Exception as e:
                pass
        
        # Attendre les notifications
        start_time = time.time()
        notification_received = False
        
        while time.time() - start_time < timeout:
            if peripheral.waitForNotifications(1.0):
                notification_received = True
                # Continuer à écouter un peu plus pour obtenir toutes les notifications
                time.sleep(2)
                break
            
            # Afficher un point toutes les 5 secondes pour montrer que c'est actif
            if int(time.time() - start_time) % 5 == 0:
                remaining = int(timeout - (time.time() - start_time))
                print(f"  ⏱️  {remaining}s restantes... (appuyez sur le bouton du capteur)")
                time.sleep(1)
        
        if not notification_received:
            print("\n⚠️  Aucune notification reçue")
            print("   Essayez d'appuyer sur le bouton du capteur")
        else:
            print("\n✓ Notification reçue avec succès")
            
            # Essayer de lire les données mises à jour
            print("\n📊 Lecture des données actualisées...")
            try:
                data = peripheral.readCharacteristic(0x0036)
                hex_data = ' '.join([f'{b:02x}' for b in data])
                print(f"  Handle 0x0036: {hex_data} ({len(data)} octets)")
                
                if len(data) >= 5:
                    temp_raw = struct.unpack('<H', data[:2])[0]
                    humidity = data[2]
                    temperature = temp_raw / 100.0
                    print(f"\n  🌡️  Température: {temperature:.1f}°C")
                    print(f"  💧 Humidité: {humidity}%")
            except:
                pass
                
            # Essayer aussi le handle 0x003a
            try:
                data = peripheral.readCharacteristic(0x003a)
                hex_data = ' '.join([f'{b:02x}' for b in data])
                print(f"  Handle 0x003a: {hex_data} ({len(data)} octets)")
                
                if len(data) >= 3:
                    temp_raw = struct.unpack('<H', data[:2])[0]
                    humidity = data[2]
                    temperature = temp_raw / 100.0
                    print(f"\n  🌡️  Température: {temperature:.1f}°C")
                    print(f"  💧 Humidité: {humidity}%")
            except:
                pass
        
        peripheral.disconnect()
        
    except Exception as e:
        print(f"✗ Erreur: {e}")


def main():
    """Fonction principale"""
    
    print("="*70)
    print("  Lecture des capteurs Xiaomi via notifications BLE")
    print("  Pour capteurs Hardware 0159")
    print("="*70)
    
    # Capteurs à tester
    sensors = [
        "A4:C1:38:9D:9E:0D",  # Capteur Hardware 0159
        # "A4:C1:38:24:E3:4D",
        # "A4:C1:38:CB:F1:95",
        # "A4:C1:38:EF:03:BD",
        # "A4:C1:38:1E:9C:7F",
    ]
    
    for sensor in sensors:
        read_with_notification(sensor, timeout=30)
        print("\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interruption par l'utilisateur")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Erreur: {e}")
        sys.exit(1)
