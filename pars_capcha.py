import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import urllib.parse
from bs4 import BeautifulSoup
from pprint import pprint
import re
from urllib.request import urlretrieve
import time
import sqlite3
from captcha_solver import CaptchaSolver

#TODO многопоточность
#TODO проверка, есть ли данные об организации в БД (пропускать, если уже есть)


count=0


def get_data(org_inn):

	def send_bot_kapcha():
		print('запрос капчи')
		kapcha = requests.get('https://www.list-org.com/bot', headers=head, verify=False)
		kapcha_img = requests.get(f"https://www.list-org.com/kcap.php?PHPSESSID={kapcha.cookies['PHPSESSID']}", cookies=kapcha.cookies, headers=head, verify=False)
		with open('kapcha.jfif', 'wb') as img:
			img.write(kapcha_img.content)
		solver = CaptchaSolver('2captcha', api_key='0000000000000000000000000')
		raw_data = open('kapcha.jfif', 'rb').read()
		try:
			answer = solver.solve_captcha(raw_data)
			def input_kapcha(message, cookies):
				input_resp = requests.post('https://www.list-org.com/bot', data={f'keystring':message.lower(),'submit':' Проверить! '}, cookies=cookies, headers=head, verify=False)
				if 'Expires' in input_resp.headers:
					print('повторный ', end='')
					send_bot_kapcha()
				else: print('капча принята')
			try:
				input_kapcha(answer, kapcha.cookies)
			except:
				send_bot_kapcha()
		except: send_bot_kapcha()

	con = sqlite3.connect("arb.db", check_same_thread=False)
	cursor = con.cursor()

	global count 
	head = {"user-agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.111 Safari/537.36"}
	resp = requests.get(f'https://www.list-org.com/search?type=inn&val={org_inn}', headers=head, verify=False) #5406590536
	if 'Expires' in resp.headers:
		send_bot_kapcha()
		resp = requests.get(f'https://www.list-org.com/search?type=inn&val={org_inn}', headers=head, verify=False) #5406590536
	soup = BeautifulSoup(resp.text, 'lxml')
	orgs = soup.find_all('label')
	org_list = {}
	for org in orgs:
		org_list.update({org.a['href']:	{'data-id': org.input['data-id'], 'name':org.a.text.strip()}})
	for org in org_list:
		count =+ count+1
		print(count)
		resp = requests.get(f"https://www.list-org.com{org}", headers=head, verify=False)
		if 'Expires' in resp.headers:
			send_bot_kapcha()
			resp = requests.get(f"https://www.list-org.com{org}", headers=head, verify=False)
		soup = BeautifulSoup(resp.text, 'lxml')
		ajax = re.findall("var erl='(.+)'", resp.text)[0]
		requisite = soup.find_all('div', class_='c2m')[2]
		inn = re.findall('\d+', requisite.find_all('p')[0].text)[0]
		try:
			kpp = re.findall('\d+', requisite.find_all('p')[1].text)[0]
		except: kpp = ''
		try:
			ogrn = re.findall('\d+', requisite.find_all('p')[3].text)[0]
		except: ogrn = ''
		org_list[org].update({'inn':inn, 'kpp':kpp, 'ogrn':ogrn})
		try:
			#смотрим последние 3 арбитражных дела
			resp = requests.get(f'https://www.list-org.com/ajax.php?md=lo&id={ajax}', headers=head, verify=False)
			if 'Expires' in resp.headers:
				send_bot_kapcha()
				resp = requests.get(f'https://www.list-org.com/ajax.php?md=lo&id={ajax}', headers=head, verify=False)
			org_list[org].update({'quantity': resp.json()['arb_cnt'], 'arb':resp.json()['arb']})
			try:
				#смотрим остальные дела
				resp = requests.get(f'https://www.list-org.com/ajax.php?md=arb&id={ajax}', headers=head, verify=False)
				if 'Expires' in resp.headers:
					send_bot_kapcha()
					resp = requests.get(f'https://www.list-org.com/ajax.php?md=arb&id={ajax}', headers=head, verify=False)
				for case in resp.json()['arb']:
					org_list[org]['arb'].append(case)
			except: pass
		except: org_list[org].update({'quantity': 0, 'arb':[]})

		# лезем в каждое дело и смотрим данные по сторонам
		# если просматриваемая организация истец - смотрим ответчика, если ответчик - истца
		for case in org_list[org]['arb']:
			other_side = 'Пятое-Десятое-вообще-насрать'
			if case['side']=='Истец':
				other_side = 'Ответчик'
			if case['side']=='Ответчик':
				other_side = 'Истец'
			try:
				resp = requests.get(f"https://www.list-org.com/arbitr/{case['id']}", headers=head, verify=False)
				if 'Expires' in resp.headers:
					send_bot_kapcha()
					resp = requests.get(f"https://www.list-org.com/arbitr/{case['id']}", headers=head, verify=False)
				soup = BeautifulSoup(resp.text, 'lxml')
				party = soup.find_all('li')
				other_sides = []
				for li in party:
					if other_side in li.text:
						defendant = li.find_all('p')
						for p in defendant:
							if 'Наименование:' in p.text:
								def_name = p.text.replace('Наименование:', '').strip()
							if 'ИНН:' in p.text:
								def_inn = p.text.replace('ИНН:', '').strip()
						other_sides.append([other_side, def_inn, def_name])
				case.update({'other_sides':other_sides})
			except: case.update({'other_sides':[]})



	for org in org_list:
		cursor.execute("""INSERT INTO org (data_id, inn, kpp, ogrn, name, arb_quantity) 
										VALUES (?, ?, ?, ?, ?,?)""", 
														(org_list[org]['data-id'], org_list[org]['inn'],
														org_list[org]['kpp'],org_list[org]['ogrn'],
														org_list[org]['name'],len(org_list[org]['arb'])))
		for issue in org_list[org]['arb']:
			cursor.execute("""INSERT INTO arb (data_id, inn, kpp, ogrn, date, arb_id, arb_name, arb_num, side, sum, text) 
									VALUES (?, ?,	?, ?, ?, ?, ?, ?, ?, ?, ?)""",
													(org_list[org]['data-id'], org_list[org]['inn'], org_list[org]['kpp'], org_list[org]['ogrn'], 
													issue['date'], issue['id'], issue['name'], issue['num'], issue['side'], issue['sum'], issue['text']))
			for other_side in issue['other_sides']:
				cursor.execute(f"""INSERT INTO other_sides (arb_id, arb_num, text, side, inn, name)
									VALUES (?, ?, ?, ?, ?, ?)""", 
													(issue['id'], issue['num'], issue['text'],
													other_side[0], other_side[1], other_side[2]))
		con.commit()


inn = """сюда пишем инн через запятую"""
for i in inn.split(','):
	get_data(i)