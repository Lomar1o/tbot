from collections import defaultdict
from math import radians, cos, sin, asin, sqrt
from boto.s3.connection import S3Connection
import telebot
import redis
import os


bot = telebot.TeleBot('1312721883:AAE_gCmhvN6uLroiRZWMIsF7R12fzK-ZIZ4')
r = redis.StrictRedis(decode_responses=True)
START, ADD, NEARBY = map(str, range(3))
STATUS = defaultdict(lambda: START)


def create_key(user_id, key):
    return f'{user_id}_{key}'


def update_state(user_id, state):
    key = create_key(user_id, 'state')
    r.set(key, state)


def get_status(user_id):
    key = create_key(user_id, 'state')
    return r.get(key)


def keyboard_add():
    keyboard = telebot.types.InlineKeyboardMarkup(row_width=2)
    buttons = ['Добавить место', 'Посмотреть', 'Отменить добавление']
    buttons = [telebot.types.InlineKeyboardButton(text=button, callback_data=button)
               for button in buttons]
    keyboard.add(*buttons)
    return keyboard


def distance(lat_from, lon_from, lat_to, lon_to):
    lon_from, lat_from, lon_to, lat_to = map(radians, (lon_from, lat_from, lon_to, lat_to))
    dlon = lon_to - lon_from
    dlat = lat_to - lat_from
    a = sin(dlat / 2) ** 2 + cos(lat_from) * cos(lat_to) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    km = 6367 * c
    return km * 1000


@bot.message_handler(func=lambda message: get_status(message.chat.id) == START,
                     commands=['add'])
def handle_massage(message):
    bot.send_message(chat_id=message.chat.id,
                     text='Вы можете добавить фото, геолокацию и название места')
    update_state(message.chat.id, ADD)


@bot.message_handler(func=lambda message: get_status(message.chat.id) == ADD,
                     content_types=['location'])
def handle_geo(message=None):
    key = create_key(message.chat.id, 'geo')
    lat = message.location.latitude
    lon = message.location.longitude
    loc = f'{lat}, {lon}'
    r.set(key, loc)
    bot.send_message(chat_id=message.chat.id, text='Геолокация обновлена',
                     reply_markup=keyboard_add())


@bot.message_handler(func=lambda message: get_status(message.chat.id) == ADD,
                     content_types=['text'])
def handle_name(message):
    key = create_key(message.chat.id, 'name')
    r.set(key, message.text)
    if message.text in ('/add', '/list', '/reset'):
        bot.send_message(chat_id=message.chat.id,
                         text='Сначала закончите добавление текущего места')
    else:
        bot.send_message(chat_id=message.chat.id, text='Название обновлено',
                         reply_markup=keyboard_add())


@bot.message_handler(func=lambda message: get_status(message.chat.id) == ADD,
                     content_types=['photo'])
def handle_img(message):
    key = create_key(message.chat.id, 'img')
    r.set(key, message.photo[0].file_id)
    bot.send_message(chat_id=message.chat.id, text='Фотография обновлена',
                     reply_markup=keyboard_add())


@bot.callback_query_handler(func=lambda x: True)
def callback_handler(callback_query):
    text = callback_query.data
    user_id = callback_query.message.chat.id
    img = r.get(create_key(user_id, 'img')) \
        if r.get(create_key(user_id, 'img')) is not None else ''
    name = r.get(create_key(user_id, 'name')) \
        if r.get(create_key(user_id, 'name')) is not None else ''
    geo = r.get(create_key(user_id, 'geo')) \
        if r.get(create_key(user_id, 'geo')) is not None else ''
    if text == 'Добавить место':
        r.lpush(user_id, f'{img}; {name}; {geo}')
        bot.send_message(chat_id=user_id, text='Место удачно добавлено')
        update_state(user_id, START)
        r.delete(create_key(user_id, 'name'))
        r.delete(create_key(user_id, 'img'))
        r.delete(create_key(user_id, 'geo'))
    elif text == 'Посмотреть':
        if img:
            bot.send_photo(chat_id=user_id, photo=img,
                           caption=f'Название места: {name}')
        elif name and not img:
            bot.send_message(chat_id=user_id, text=f'Название места: {name}')
        if geo:
            bot.send_location(user_id, geo.split()[0], geo.split()[1])
    elif text == 'Отменить добавление':
        r.delete(create_key(user_id, 'name'))
        r.delete(create_key(user_id, 'img'))
        r.delete(create_key(user_id, 'geo'))
        update_state(user_id, START)


@bot.message_handler(func=lambda message: get_status(message.chat.id) == START,
                     commands=['list'])
def handle_list(message):
    user_id = message.chat.id
    # r.delete(user_id)
    res = r.lrange(message.chat.id, 0, 10)
    if not res:
        bot.send_message(chat_id=message.chat.id, text='Места пока не добавлены')
    for place in res:
        img, name, geo = place.split(';')
        if img:
            bot.send_photo(chat_id=user_id, photo=img,
                           caption=f'Название места: {name}')
        elif name and not img:
            bot.send_message(chat_id=user_id, text=f'Название места: {name}')
        try:
            print(geo, name)
            bot.send_location(user_id, geo.split()[0], geo.split()[1])
        except IndexError:
            pass


@bot.message_handler(func=lambda x: True, commands=['start'])
def handle_information(message):
    bot.send_message(chat_id=message.chat.id, text='Введите команду /add для добавления локации')
    bot.send_message(chat_id=message.chat.id,
                     text='Введите команду /list для просмотра 10 последних локаций')
    bot.send_message(chat_id=message.chat.id,
                     text='Введите команду /reset для удаления всех локаций')


@bot.message_handler(commands=['reset'])
def handle_reset(message):
    r.delete(message.chat.id)
    bot.send_message(chat_id=message.chat.id, text='Все места удалены')


@bot.message_handler(commands=['nearby'])
def handle_nearby(message):
    bot.send_message(chat_id=message.chat.id,
                     text='Добавьте геолокацию, чтоб получить ближайшие добавленные места')
    bot.send_message(chat_id=message.chat.id, text='Введите в каком радиусе искать места')
    update_state(message.chat.id, NEARBY)


@bot.message_handler(func=lambda message: get_status(message.chat.id) == NEARBY,
                     content_types=['location', 'text'])
def handle_nearby_place(message):
    user_id = message.chat.id
    key = create_key(user_id, 'dis')
    if message.text:
        if message.text.isdigit():
            r.set(key, message.text)
            bot.send_message(chat_id=user_id, text='Теперь добавьте геолокацию')
        else:
            bot.send_message(chat_id=user_id, text='Введите число')
    elif message.location:
        lat_from = message.location.latitude
        lon_from = message.location.longitude
        places = r.lrange(message.chat.id, 0, -1)
        for place in places:
            try:
                img, name, geo = place.split(';')
                lat_to, lon_to = map(float, geo.split(','))
                dis = distance(lat_from, lon_from, lat_to, lon_to)
                if dis <= float(r.get(key)):
                    bot.send_message(chat_id=user_id, text=f'{name}')
                    bot.send_location(user_id, lat_to, lon_to)
            except IndexError:
                continue
        update_state(user_id, START)


bot.polling()
