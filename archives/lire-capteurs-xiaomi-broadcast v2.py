#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script pour lire les capteurs Xiaomi via les publicités BLE
Format ATC (firmware pvvx)
Envoie les données dans TimescaleDB
"""

import sys
from bluepy import btle
import struct
from datetime import datetime
import psycopg2
import config

class XiaomiAdvertisementScanner(btle.DefaultDelegate):
    """Scanner de publicités BLE pour capteurs Xiaomi"""
    
    def __init__(self, sensors_dict=None):
        btle.DefaultDelegate.__init__(self)
        self.sensors_dict = sensors_dict or {}
        self.devices_data = {}
        
    def handleDiscovery(self, dev, isNewDev, isNewData):
        """Appelé pour chaque appareil découvert ou mis à jour"""
        if self.sensors_dict and dev.addr.upper() not in self.sensors_dict:
            return
        
        # N'afficher qu'une fois par capteur
        if dev.addr.upper() in self.devices_data:
            return
            
        for (adtype, desc, value) in dev.getScanData():
            # Service Data - UUID 0x181a (ATC format)
            if adtype == 22 and value.startswith('1a18'):
                self.parse_atc_format(dev.addr.upper(), value, dev.rssi)
                break  # Une seule fois par capteur
    
    def parse_atc_format(self, mac, data, rssi):
        """Parse le format ATC (UUID 0x181a)"""
        try:
            bytes_data = bytes.fromhex(data)
            if len(bytes_data) < 13:
                return
            
            payload = bytes_data[2:]  # Ignorer UUID
            
            # Temperature (2 octets) - signed int16, big endian, en dixièmes de degré
            temp_raw = struct.unpack('>h', payload[6:8])[0]
            temperature = temp_raw / 10.0
            
            # Humidity (1 octet)
            humidity = payload[8]
            
            # Battery % (1 octet)
            battery_pct = payload[9]
            
            # Battery mV (2 octets) - unsigned int16, big endian
            battery_mv = struct.unpack('>H', payload[10:12])[0]
            
            # Counter (1 octet)
            counter = payload[12] if len(payload) > 12 else 0
            
            # Récupérer le nom du capteur
            name = self.sensors_dict.get(mac, "???")
            
            # Affichage sur une seule ligne
            print(f"{name}  {mac}  🌡️ {temperature:5.1f}°C  💧 {humidity:2d}%  🔋 {battery_pct:3d}% ({battery_mv} mV)  📡 {rssi:3d} dBm  🔢 {counter:3d}")
            
            # Stockage
            self.devices_data[mac] = {
                'name': name,
                'temperature': temperature,
                'humidity': humidity,
                'battery': battery_pct,
                'battery_mv': battery_mv,
                'rssi': rssi,
                'counter': counter,
                'timestamp': datetime.now()
            }
            
            # Écriture dans TimescaleDB
            if self.db_conn:
                self.write_timescaledb(mac, name, temperature, humidity, battery_pct, battery_mv)
            
        except Exception as e:
            pass
    
    def write_timescaledb(self, mac, capteur, temperature, humidity, battery_pct, battery_mv):
        """Écrit les données dans TimescaleDB"""
        try:
            cursor = self.db_conn.cursor()
            timestamp = datetime.now()
            
            # Insertion température
            query = """
                INSERT INTO sensor_data (time, mac, capteur, measurement, value)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(query, (timestamp, mac, capteur, 'MI_TEMPERATURE', temperature))
            
            # Insertion humidité
            cursor.execute(query, (timestamp, mac, capteur, 'MI_HUMIDITY', humidity))
            
            # Insertion batterie (%)
            cursor.execute(query, (timestamp, mac, capteur, 'MI_BATTERY', battery_pct))
            
            # Insertion voltage batterie (mV)
            cursor.execute(query, (timestamp, mac, capteur, 'MI_BATTERY_MV', battery_mv))
            
            self.db_conn.commit()
            cursor.close()
        except Exception as e:
            print(f"✗ Erreur TimescaleDB pour {capteur}: {e}")
            self.db_conn.rollback()


def scan_advertisements(sensors_dict, duration=30):
    """Scanner les publicités BLE des capteurs"""
    
    scanner = btle.Scanner()
    delegate = XiaomiAdvertisementScanner(sensors_dict)
    scanner.withDelegate(delegate)
    
    try:
        print(f"🔍 Scan des capteurs ({duration}s)...\n")
        
        # Scanner jusqu'à ce que tous les capteurs soient trouvés ou timeout
        start_time = datetime.now()
        while (datetime.now() - start_time).seconds < duration:
            scanner.scan(2.0, passive=False)
            
            # Arrêter si tous les capteurs sont trouvés
            if len(delegate.devices_data) >= len(sensors_dict):
                break
        
        print()  # Ligne vide finale
        return delegate.devices_data
        
    except btle.BTLEException as e:
        error_msg = str(e)
        if "Invalid Index" in error_msg or "le on" in error_msg:
            print("✗ Erreur Bluetooth: Adaptateur non disponible ou occupé")
            print("💡 Solutions:")
            print("   1. Vérifiez que l'adaptateur Bluetooth est activé: hciconfig")
            print("   2. Redémarrez le service Bluetooth: sudo systemctl restart bluetooth")
            print("   3. Assurez-vous qu'aucun autre processus n'utilise le BLE")
        else:
            print(f"✗ Erreur BLE: {error_msg}")
        return {}


def main():
    """Fonction principale"""
    
    # Capteurs à surveiller (MAC: Nom)
    sensors = {
        "A4:C1:38:84:F0:8C": "101",
        "A4:C1:38:EF:03:BD": "102",
        "A4:C1:38:9D:9E:0D": "103",
        "A4:C1:38:CB:F1:95": "104",
        "A4:C1:38:1E:9C:7F": "105",
    }
    
    # Scanner les publicités
    scan_advertisements(sensors, duration=30)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️  Interruption")
        sys.exit(0)
