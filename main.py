import sys
import requests
import yaml
from zoneinfo import ZoneInfo
from argparse import ArgumentParser
from datetime import datetime, timedelta

BASE_URL = 'https://portal.ufsm.br/mobile/webservice'

def read_config() -> dict:
    with open('config.yaml', 'r') as document:
        return yaml.safe_load(document)

def is_weekday(date: datetime, weekday: str) -> bool:
    return date.strftime('%a') == weekday

def resolve_restaurant_id(restaurant: int):
    match restaurant:
        case 2:
            return 41
        case _:
            return restaurant

def login(username: str, password: str) -> str:
    response = requests.post(
        f'{BASE_URL}/generateToken',
        json={
            'appName': config['environment']['app'],
            'deviceId': config['environment']['device-id'],
            'deviceInfo': config['environment']['device-info'],
            'messageToken': config['environment']['message-token'],
            'login': username,
            'senha': password
        }
    )

    data = response.json()

    if data['error']:
        raise Exception(data['mensagem'])
    
    return data['token']

def build_payload(start: datetime, end: datetime, options: dict) -> dict:
    payload = {
        'dataInicio': start.strftime('%Y-%m-%d %H:%M:%S'),
        'dataFim': end.strftime('%Y-%m-%d %H:%M:%S'),
        'idRestaurante': resolve_restaurant_id(options['restaurant']),
        'opcaoVegetariana': options['vegetarian'],
        'tiposRefeicoes': []
    }

    meals = [('coffee', 'Caf\u00e9', 1), ('lunch', 'Almo\u00e7o', 2), ('dinner', 'Janta', 3)]

    for key, label, item in meals:
        if options[key]:
            payload['tiposRefeicoes'].append({
                'descricao': label,
                'error': False,
                'item': item,
                'itemId': item,
                'selecionado': True
            })

    return payload

def schedule_meal(token: str, start: datetime, end: datetime, options: dict) -> list:
    response = requests.post(
        f'{BASE_URL}/ru/agendaRefeicoes',
        json=build_payload(start, end, options),
        headers={
            'X-UFSM-Device-ID': config['environment']['device-id'],
            'X-UFSM-Access-Token': token
        }
    )

    return response.json()

def find_schedules(date):
    filtered_schedules = filter(
        lambda s : is_weekday(date, s['weekday']),
        config['schedules']
    )

    return list(filtered_schedules)

parser = ArgumentParser(
    prog='ruina',
    description='Agenda automaticamente as refei\u00e7\u00f5es do RU da UFSM.'
)

parser.add_argument('-u', '--username', dest='username', help='Sua matr\u00edcula do aplicativo da UFSM.')
parser.add_argument('-p', '--password', dest='password', help='Sua senha do aplicativo da UFSM.')

args = parser.parse_args()

print('Lendo configura\u00e7\u00e3o...')
config = read_config()

print('Procurando refei\u00e7\u00f5es para serem agendadas amanh\u00e3...')
now = datetime.now(ZoneInfo('America/Sao_Paulo'))
tomorrow = now + timedelta(1)

tomorrow_schedules = find_schedules(tomorrow)

if len(tomorrow_schedules) != 0:
    print(f'Encontrado {len(tomorrow_schedules)} refei\u00e7\u00e3o(s) para serem agendadas.')

    try:
        print('Logando no aplicativo...')
        access_token = login(args.username, args.password)
    except Exception as exception:
        print(f'Falha ao logar: {str(exception)}')
    else:
        failed = False

        for schedule in tomorrow_schedules:
            print(f"Agendando refei\u00e7\u00f5es para o RU {schedule['restaurant']}... ({schedule})")

            response = schedule_meal(access_token, tomorrow, tomorrow, schedule)

            if isinstance(response, dict):
                if response.get('error'):
                    print(f"[Erro] {response.get('mensagem')}")
                    failed = True

                statuses = (
                    response.get('refeicoes')
                    or response.get('agendamentos')
                    or response.get('lista')
                    or []
                )
            elif isinstance(response, list):
                statuses = response
            else:
                print(f'[Erro] Resposta inesperada: {type(response).__name__}')
                statuses = []
                failed = True

            if not statuses:
                print('[Erro] A API nao retornou nenhum status de agendamento.')
                failed = True

            for status in statuses:
                if not isinstance(status, dict):
                    print(f'[Erro] Status inesperado: {type(status).__name__}')
                    failed = True
                    continue

                raw_date = (
                    status.get('dataRefAgendada')
                    or status.get('dataRefeicao')
                    or status.get('data')
                )
                meal = status.get('tipoRefeicao') or status.get('descricao') or '?'
                label = raw_date.split(' ')[0] if isinstance(raw_date, str) else '?'
                message = f"{label} - RU {schedule['restaurant']} ({meal}): "

                if status.get('sucesso'):
                    print(message + 'Agendado com sucesso.')
                else:
                    reason = (
                        status.get('impedimento')
                        or status.get('mensagem')
                        or 'motivo nao informado'
                    )
                    print('[Erro] ' + message + str(reason) + '.')
                    failed = True

        if failed:
            sys.exit(1)
else:
    print('N\u00e3o h\u00e1 nenhuma refei\u00e7\u00e3o para ser agendada amanh\u00e3.')
