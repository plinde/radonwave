#!/usr/bin/env python3
import sys
import time
from struct import unpack
from bluepy import btle
import time
from argparse import ArgumentParser
import json, os, paho.mqtt.client as paho

class CouldNotConnectError(Exception):
	pass


class Measurement:
	def __init__(self, humidity, temperature, radon_avg, radon_1day, accel, humidity2):
		self.humidity = humidity
		self.temperature = temperature
		self.radon_avg = radon_avg
		self.radon_1day = radon_1day
		self.accel = accel
		self.humidity2 = humidity2


def connect_and_read(device_address):
	try:
		dev = btle.Peripheral(device_address)
	except btle.BTLEException as e:
		raise CouldNotConnectError()

	# Humidity: 00002a6f-0000-1000-8000-00805f9b34fb
	# Temperature: ...
	# Radon conc. average: b42e0a4c-ade7-11e4-89d3-123b93f75cba
	# Radon conc. 1 day: b42e01aa-ade7-11e4-89d3-123b93f75cba

	if False:
		print('Services')
		for service in dev.services:
			print(service)

		print('Characteristics')
		for ch in dev.getCharacteristics():
			print(ch.getHandle(), ch.uuid, ch.propertiesToString())

	service = dev.getServiceByUUID(btle.UUID('b42e1f6e-ade7-11e4-89d3-123b93f75cba'))

	temperature = humidity = radon_avg = radon_1day = accel = humidity2 = None
	for ch in service.getCharacteristics():
		name = ch.uuid.getCommonName()
		if name == 'Temperature':
			value = unpack('h', ch.read())[0]
			temperature = value / 100
		elif name == 'Humidity':
			value = unpack('h', ch.read())[0]
			humidity = value/100
		elif name == 'b42e0a4c-ade7-11e4-89d3-123b93f75cba':
			# Description: 'Radon conc. avg.'
			value = unpack('h', ch.read())[0]
			radon_avg = value
		elif name == 'b42e01aa-ade7-11e4-89d3-123b93f75cba':
			# Description: 'Radon conc. 1 day'
			value = unpack('h', ch.read())[0]
			radon_1day = value
		elif name == 'b42e1096-ade7-11e4-89d3-123b93f75cba':
			# Description: 'Accel. Light 5m'
			accel = unpack('H', ch.read())[0]
		elif name == 'b42e1348-ade7-11e4-89d3-123b93f75cba':
			# Description: 'Status info'
			# Seems to be identical to humidity
			humidity2 = unpack('h', ch.read())[0] / 100
	dev.disconnect()
	return Measurement(humidity=humidity, temperature=temperature,
		radon_avg=radon_avg, radon_1day=radon_1day, accel=accel,
		humidity2=humidity2)

def mqtt_connect():
	mqtt_host=os.environ['mqtt_host']
	mqtt_port=int(os.environ['mqtt_port'])
	mqtt_username=os.environ['mqtt_username']
	mqtt_password=os.environ['mqtt_password']
	mqtt_client=os.environ['mqtt_client']

	mqtt_client = paho.Client(mqtt_client)                           #create client object
	mqtt_client.username_pw_set(mqtt_username, password=mqtt_password)
	mqtt_client.on_publish = mqtt_onpublish                          #assign function to callback
	mqtt_client.connect(mqtt_host,port=mqtt_port)                                 #establish connection

	return mqtt_client

def mqtt_onpublish(client,userdata,result):             #create function for callback
	print("data published \n")
	# print("client: %s \n") % (client)
	# print("userdata: %s \n") % (userdata)
	# print("result: %s \n") % (result)
	pass



def main():
	parser = ArgumentParser()
	parser.add_argument('--wait', default=1200, type=int,
		help='Seconds to wait between queries. Do not choose this too low as the '
		'radon levels are only updated once every 60 minutes. Default: 1200 '
		'(20 minutes)')
	parser.add_argument('device_address', metavar='BLUETOOTH-DEVICE-ADDRESS')
	args = parser.parse_args()
	device_address = args.device_address
	mqtt_client = mqtt_connect()
	mqtt_topic = os.environ['mqtt_topic']

	while True:
		try:
			measurement = connect_and_read(device_address)
		except CouldNotConnectError:
			print('Could not connect', file=sys.stderr)
		except btle.BTLEException as e:
			print('Bluetooth error:', e, file=sys.stderr)
		else:
			print('{time}\t{temperature:.2f}\t{humidity:.2f}\t{radon_avg}\t{radon_1day}\t{accel:04X}\t{humidity2:.2f}'.format(
				time=time.strftime('%Y-%m-%d %H:%M:%S'),
				**vars(measurement)
				), sep='\t')
			sys.stdout.flush()

			data = {}
			data['time'] = time.strftime('%Y-%m-%d %H:%M:%S')
			data['temperature'] = "%s" % (measurement.temperature)
			data['humidity'] = "%s" % (measurement.humidity)
			data['radon_avg'] = "%s" % (measurement.radon_avg)
			data['radon_1day'] = "%s" % (measurement.radon_1day)
			data['accel'] = "%s" % (measurement.accel)
			data['humidity2'] = "%s" % (measurement.humidity2)
			json_data = json.dumps(data)
			print(json_data)

			ret = mqtt_client.publish(mqtt_topic, json_data)

		time.sleep(args.wait)


if __name__ == '__main__':
	main()
