# Продаём рыбу в телеграме
Данный проект позволяет с помощью `бота` покупать покупать рыбу в `телеграме`.
Ознакомиться с работой `бота` можете по [ссылке](https://t.me/norgius_speech_bot).

## Что необходимо для запуска
Для данного проекта необходим `Python3.6` (или выше).
Создадим виртуальное окружение в корневой директории проекта:
```
python3 -m venv env
```
После активации виртуального окружения установим необходимые зависимости:
```
pip install -r requirements.txt
```
Также заранее создадим файл `.env` в директории проекта.

## Создаем магазин на сайте [Elasticpath](https://www.elasticpath.com/)
Зарегистрируйтесь как разработчик на сайте [Elasticpath](https://www.elasticpath.com/). В личном кабинете вы сможете создавать товары, не забудьте указать цену, доступное количество на складе и привязать картинки для ваших продуктов. Созданные товары необходимо связать иерархией с каталогом.

Для телеграм бота потребуются `Client ID` и `Client Secret`, запишите их в `.env`:
```
ELASTICPATH_CLIENT_SECRET=
ELASTICPATH_CLIENT_ID=
```

## Создаём бота
Напишите [отцу ботов](https://telegram.me/BotFather) для создания телеграм бота.

Запишите его токен в `.env`:
```
FISH_SHOP_BOT_TG_TOKEN=
```

## Подключаем Redis
Регистрируемся на [Redis](https://redis.com/) и заводим себе удаленную `базу данных`. Для подключения к ней вам понадобятся `host`, `port` и `password`. Запишите их в файле `.env`:
```
REDIS_HOST=
REDIS_PORT=
REDIS_PASSWORD=
```

## Запуск бота
Бот запускается командой
```
python bot.py
```
