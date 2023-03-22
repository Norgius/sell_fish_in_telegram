import logging
from textwrap import dedent
from functools import partial

import redis
import requests
from validate_email import validate_email
from environs import Env
from telegram import ParseMode
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Filters, Updater, CallbackContext
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler

from api_functions import (get_access_token, get_products, get_product_image,
                           put_product_in_cart, get_user_cart, create_customer,
                           delete_cart_product, delete_all_cart_products)

logger = logging.getLogger(__name__)
_database = None


def parse_products(raw_products: list, inventories: list) -> dict:
    products = {}
    for raw_product in raw_products:
        attributes = raw_product.get('attributes')
        product = {
            'name': attributes.get('name'),
            'description': attributes.get('description'),
            'price': attributes.get('price').get('USD').get('amount') / 100,
            'image_id': raw_product.get('relationships')
            .get('main_image').get('data').get('id')
            }
        products[raw_product.get('id')] = product
    for inventory in inventories:
        products.get(inventory.get('id'))['stock'] = inventory.get('available')
    return products


def get_menu_buttons(products: dict) -> list:
    keyboard = []
    for product_id, product in products.items():
        button = [
            InlineKeyboardButton(product.get('name'), callback_data=product_id)
                  ]
        keyboard.append(button)
    keyboard.append([InlineKeyboardButton('Корзина', callback_data='Корзина')])
    return keyboard


def get_product_quantity_in_cart(product_id, user_cart):
    products = user_cart.get('data')
    if products:
        for product in products:
            if product_id == product.get('product_id'):
                return int(product.get('quantity'))
    return 0


def prepare_cart_buttons_and_message(user_cart):
    products = user_cart.get('data')
    message = ''
    keyboard = []
    if products:
        for product in products:
            product_price = product.get('meta').get('display_price')\
                .get('without_tax').get('unit').get('formatted')
            product_quantity = product.get('quantity')
            product_total_cost = product_quantity * float(product_price[1::])

            message += dedent(f'''
            <b>{product.get("name")}</b>

            {product.get("description")}
            <u>{product_price}</u> за кг
            <u>{product_quantity}кг</u> в корзине за <u>${product_total_cost:.2f}</u>
            ''')
            button = [InlineKeyboardButton(
                f'Убрать из корзины {product.get("name")}',
                callback_data=f'del_{product.get("id")}'
                                           )
                      ]
            keyboard.append(button)
        cart_total_cost = user_cart.get('meta').get('display_price')\
            .get('without_tax').get('formatted')
        message += dedent(f'''
        <b>Общая стоимость:</b> <u>{cart_total_cost}</u>''')
    else:
        message = 'Ваша корзина пуста'

    keyboard.append([InlineKeyboardButton('В меню', callback_data='В меню')])
    if len(keyboard) > 1:
        keyboard.append(
            [InlineKeyboardButton('Оплатить', callback_data='Оплатить')]
        )
    reply_markup = InlineKeyboardMarkup(keyboard)
    return message, reply_markup


def prepare_description_buttons_and_message(product_data, product_quantity):
    message = dedent(f'''
    <b>{product_data.get('name')}</b>

    <u>{product_data.get('price'):.2f}$</u> за 1 кг
    <u>{product_data.get('stock')}кг</u> на складе

    {product_data.get('description')}
    ''')
    if product_quantity:
        message += dedent(f'''
        В вашей <b>корзине</b> <u>{product_quantity} кг</u> данного товара
        ''')
    keyboard = [
        [InlineKeyboardButton('1 кг', callback_data='1 кг'),
         InlineKeyboardButton('5 кг', callback_data='5 кг'),
         InlineKeyboardButton('10 кг', callback_data='10 кг')],
        [InlineKeyboardButton('Корзина', callback_data='Корзина')],
        [InlineKeyboardButton('Назад', callback_data='Назад')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    return message, reply_markup


def start(update: Update, context: CallbackContext) -> str:
    store_access_token = context.bot_data['store_access_token']
    raw_products, inventories = get_products(store_access_token)
    products = parse_products(raw_products, inventories)
    keyboard = get_menu_buttons(products)
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(text='Пожалуйста, выберите товар!',
                              reply_markup=reply_markup)
    return 'HANDLE_MENU'


def handle_menu(update: Update, context: CallbackContext) -> str:
    bot = context.bot
    query = update.callback_query
    if not query:
        return 'HANDLE_MENU'
    chat_id = query.message.chat_id
    user_reply = query.data
    store_access_token = context.bot_data['store_access_token']
    user_cart = get_user_cart(store_access_token, chat_id)
    if user_reply == 'Корзина':
        message, reply_markup = prepare_cart_buttons_and_message(user_cart)
        bot.send_message(chat_id=chat_id, text=message,
                         reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        bot.delete_message(chat_id=chat_id,
                           message_id=query.message.message_id)
        return 'HANDLE_CART'
    raw_products, inventories = get_products(store_access_token)
    products = parse_products(raw_products, inventories)
    context.bot_data['product_id'] = user_reply
    product_data = products.get(user_reply)
    context.bot_data[f'{user_reply}_data'] = product_data

    image_id = product_data.get('image_id')
    image = get_product_image(store_access_token, image_id)
    quantity_in_cart = get_product_quantity_in_cart(user_reply, user_cart)
    message, reply_markup = prepare_description_buttons_and_message(
        product_data, quantity_in_cart)

    bot.send_photo(chat_id=chat_id, photo=image, caption=message,
                   reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    bot.delete_message(chat_id=chat_id,
                       message_id=query.message.message_id)
    return 'HANDLE_DESCRIPTION'


def handle_description(update: Update, context: CallbackContext) -> str:
    bot = context.bot
    query = update.callback_query
    if not query:
        return 'HANDLE_DESCRIPTION'
    user_reply = query.data
    chat_id = query.message.chat_id
    store_access_token = context.bot_data['store_access_token']
    if user_reply in ['1 кг', '5 кг', '10 кг']:
        product_id = context.bot_data['product_id']
        product_data = context.bot_data[f'{product_id}_data']
        quantity = int(user_reply.split()[0])
        user_cart = put_product_in_cart(store_access_token, product_id,
                                        quantity, chat_id)
        bot.answer_callback_query(text='Товар добавлен к корзину',
                                  callback_query_id=query.id,)

        quantity_in_cart = get_product_quantity_in_cart(product_id, user_cart)
        message, reply_markup = prepare_description_buttons_and_message(
            product_data, quantity_in_cart)
        image_id = product_data.get('image_id')
        image = get_product_image(store_access_token, image_id)
        bot.send_photo(chat_id=chat_id, photo=image, caption=message,
                       reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        bot.delete_message(chat_id=chat_id,
                           message_id=query.message.message_id)
        return 'HANDLE_DESCRIPTION'
    elif user_reply == 'Корзина':
        user_cart = get_user_cart(store_access_token, chat_id)
        message, reply_markup = prepare_cart_buttons_and_message(user_cart)
        bot.send_message(chat_id=chat_id, text=message,
                         reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        bot.delete_message(chat_id=chat_id,
                           message_id=query.message.message_id)
        return 'HANDLE_CART'
    else:
        raw_products, inventories = get_products(store_access_token)
        products = parse_products(raw_products, inventories)
        keyboard = get_menu_buttons(products)
        reply_markup = InlineKeyboardMarkup(keyboard)
        bot.send_message(text='Пожалуйста, выберите товар!', chat_id=chat_id,
                         reply_markup=reply_markup)
        bot.delete_message(chat_id=chat_id,
                           message_id=query.message.message_id)
        return 'HANDLE_MENU'


def handle_cart(update: Update, context: CallbackContext) -> str:
    bot = context.bot
    query = update.callback_query
    if not query:
        return 'HANDLE_CART'
    chat_id = query.message.chat_id
    user_reply = query.data
    store_access_token = context.bot_data['store_access_token']
    if user_reply.startswith('del_'):
        product_id = user_reply[4::]
        delete_cart_product(store_access_token, chat_id, product_id)
        user_cart = get_user_cart(store_access_token, chat_id)
        message, reply_markup = prepare_cart_buttons_and_message(user_cart)
        bot.send_message(chat_id=chat_id, text=message,
                         reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        bot.delete_message(chat_id=chat_id,
                           message_id=query.message.message_id)
        return 'HANDLE_CART'
    elif user_reply == 'В меню':
        raw_products, inventories = get_products(store_access_token)
        products = parse_products(raw_products, inventories)
        keyboard = get_menu_buttons(products)
        reply_markup = InlineKeyboardMarkup(keyboard)
        bot.send_message(text='Пожалуйста, выберите товар!',
                         chat_id=chat_id, reply_markup=reply_markup)
        bot.delete_message(chat_id=chat_id,
                           message_id=query.message.message_id)
        return 'HANDLE_MENU'
    else:
        message = 'Пришлите, пожалуйста, ваш <b>email</b>'
        bot.send_message(text=message, chat_id=query.message.chat_id,
                         parse_mode=ParseMode.HTML)
        return 'WAITING_EMAIL'


def waiting_email(update: Update, context: CallbackContext) -> str:
    bot = context.bot
    query = update.callback_query
    if query and query.data == 'Неверно':
        message = 'Пришлите, пожалуйста, ваш <b>email</b>'
        bot.send_message(text=message, chat_id=query.message.chat_id,
                         parse_mode=ParseMode.HTML)
        bot.delete_message(chat_id=query.message.chat_id,
                           message_id=query.message.message_id)
        return 'WAITING_EMAIL'
    elif query and query.data == 'Верно':
        store_access_token = context.bot_data['store_access_token']
        chat_id = query.message.chat_id
        customer_email = _database.get(f'email_{chat_id}').decode()
        if not validate_email(customer_email):
            text = dedent(f'''
            Данный <b>email: {customer_email}</b> не является настоящим.
            Пожалуйста, введите актуальную почту
            ''')
            bot.send_message(text=text, chat_id=chat_id,
                             parse_mode=ParseMode.HTML)
            bot.delete_message(chat_id=chat_id,
                               message_id=query.message.message_id)
            return 'WAITING_EMAIL'
        bot.send_message(text='Ожидайте уведомление на почте', chat_id=chat_id)
        bot.delete_message(chat_id=chat_id,
                           message_id=query.message.message_id)
        if not _database.get(f'customer_{chat_id}'):
            first_name = name if (name := query.from_user.first_name) else ''
            last_name = name if (name := query.from_user.last_name) else ''
            customer_name = (first_name + ' ' + last_name).strip()
            store_access_token = context.bot_data['store_access_token']
            customer_id = create_customer(store_access_token, customer_name,
                                          customer_email)
            _database.set(f'customer_{chat_id}', customer_id)
        delete_all_cart_products(store_access_token, chat_id)
        raw_products, inventories = get_products(store_access_token)
        products = parse_products(raw_products, inventories)
        keyboard = get_menu_buttons(products)
        reply_markup = InlineKeyboardMarkup(keyboard)
        bot.send_message(text='Пожалуйста, выберите товар!', chat_id=chat_id,
                         reply_markup=reply_markup)
        return 'HANDLE_MENU'
    else:
        email = update.message.text
        message = dedent(f'''
        Вы прислали мне эту почту: <b>{email}</b>
        Всё верно?
        ''')
        chat_id = update.effective_chat.id
        _database.set(f'email_{chat_id}', email)
        keyboard = [[InlineKeyboardButton('Верно', callback_data='Верно')],
                    [InlineKeyboardButton('Неверно', callback_data='Неверно')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text(text=message, reply_markup=reply_markup,
                                  parse_mode=ParseMode.HTML)
        return 'WAITING_EMAIL'


def handle_users_reply(update: Update, context: CallbackContext,
                       client_secret: str, client_id: str,
                       token_lifetime: int) -> None:
    try:
        store_access_token = _database.get('store_access_token')
        if not store_access_token:
            store_access_token = get_access_token(client_secret, client_id)
            _database.setex('store_access_token', token_lifetime,
                            store_access_token)
        else:
            store_access_token = store_access_token.decode('utf-8')
        context.bot_data['store_access_token'] = store_access_token
    except requests.exceptions.HTTPError as err:
        logger.warning(f'Ошибка в работе api.moltin.com\n{err}\n')

    if update.message:
        user_reply = update.message.text
        chat_id = update.message.chat_id
    elif update.callback_query:
        user_reply = update.callback_query.data
        chat_id = update.callback_query.message.chat_id
    else:
        return
    if user_reply == '/start':
        user_state = 'START'
    else:
        user_state = _database.get(chat_id).decode('utf-8')

    states_functions = {
        'START': start,
        'HANDLE_MENU': handle_menu,
        'HANDLE_DESCRIPTION': handle_description,
        'HANDLE_CART': handle_cart,
        'WAITING_EMAIL': waiting_email,
    }
    state_handler = states_functions[user_state]
    try:
        next_state = state_handler(update, context)
        _database.set(chat_id, next_state)
    except requests.exceptions.HTTPError as err:
        logger.warning(f'Ошибка в работе api.moltin.com\n{err}\n')
    except Exception as err:
        logger.warning(f'Ошибка в работе телеграм бота\n{err}\n')


def get_database_connection(database_password: str, database_host: str,
                            database_port: int) -> redis.Redis:
    global _database
    if _database is None:
        _database = redis.Redis(host=database_host, port=database_port,
                                password=database_password)
    return _database


def main():
    env = Env()
    env.read_env()
    client_secret = env.str('ELASTICPATH_CLIENT_SECRET')
    client_id = env.str('ELASTICPATH_CLIENT_ID')
    token_lifetime = env.int('TOKEN_LIFETIME')
    database_password = env.str("REDIS_PASSWORD")
    database_host = env.str("REDIS_HOST")
    database_port = env.int("REDIS_PORT")
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logger.setLevel(logging.INFO)

    _ = get_database_connection(database_password, database_host,
                                database_port)
    tg_token = env.str('FISH_SHOP_BOT_TG_TOKEN')
    updater = Updater(tg_token)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CallbackQueryHandler(
        partial(handle_users_reply, client_secret=client_secret,
                client_id=client_id, token_lifetime=token_lifetime))
                           )
    dispatcher.add_handler(MessageHandler(
        Filters.text,
        partial(handle_users_reply, client_secret=client_secret,
                client_id=client_id, token_lifetime=token_lifetime))
                           )
    dispatcher.add_handler(CommandHandler(
        'start',
        partial(handle_users_reply, client_secret=client_secret,
                client_id=client_id, token_lifetime=token_lifetime))
                           )
    logger.info('Телеграм бот запущен')
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
