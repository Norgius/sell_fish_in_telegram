import requests
import redis


def get_access_token(_database: redis.Redis, client_secret: str,
                     client_id: str, token_lifetime: int) -> str:
    url = 'https://api.moltin.com/oauth/access_token'
    data = {'grant_type': 'client_credentials',
            'client_secret': client_secret, 'client_id': client_id}
    response = requests.post(url, data=data)
    response.raise_for_status()
    access_token = response.json().get('access_token')
    _database.setex('store_access_token', token_lifetime, access_token)
    return access_token


def get_products(store_access_token: str) -> tuple[list, list]:
    headers = {'Authorization': f'Bearer {store_access_token}'}
    response = requests.get('https://api.moltin.com/catalog/products',
                            headers=headers)
    response.raise_for_status()
    raw_products = response.json().get('data')
    response = requests.get('https://api.moltin.com/v2/inventories',
                            headers=headers)
    response.raise_for_status()
    inventories = response.json().get('data')
    return raw_products, inventories


def get_product_image(store_access_token: str, image_id: str):
    headers = {'Authorization': f'Bearer {store_access_token}'}
    response = requests.get(f'https://api.moltin.com/v2/files/{image_id}',
                            headers=headers)
    response.raise_for_status()
    image_link = response.json().get('data').get('link').get('href')
    response = requests.get(image_link, stream=True)
    response.raise_for_status()
    return response.raw


def put_product_in_cart(store_access_token: str, product_id: str,
                        quantity: str, chat_id: int) -> None:
    url = f'https://api.moltin.com/v2/carts/{chat_id}/items'
    headers = {'Authorization': f'Bearer {store_access_token}'}
    body = {"data": {'quantity': quantity, 'type': 'cart_item',
                     'id': product_id}}
    response = requests.post(url, headers=headers, json=body)
    response.raise_for_status()


def get_user_cart(store_access_token: str, chat_id: int) -> dict:
    url = f'https://api.moltin.com/v2/carts/{chat_id}/items'
    headers = {'Authorization': f'Bearer {store_access_token}'}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


def delete_cart_product(store_access_token: str, chat_id: int,
                        product_id: str) -> None:
    url = f'https://api.moltin.com/v2/carts/{chat_id}/items/{product_id}'
    headers = {'Authorization': f'Bearer {store_access_token}'}
    response = requests.delete(url, headers=headers)
    response.raise_for_status()


def delete_all_cart_products(store_access_token: str, chat_id: int) -> None:
    url = f'https://api.moltin.com/v2/carts/{chat_id}/items'
    headers = {'Authorization': f'Bearer {store_access_token}'}
    response = requests.delete(url, headers=headers)
    response.raise_for_status()


def create_customer(store_access_token: str, customer_name: str,
                    customer_email: str) -> str:
    url = 'https://api.moltin.com/v2/customers'
    headers = {'Authorization': f'Bearer {store_access_token}'}
    body = {"data": {'name': customer_name, 'type': 'customer',
                     'email': customer_email}}
    response = requests.post(url, headers=headers, json=body)
    response.raise_for_status()
    customer_id = response.json().get('data').get('id')
    return customer_id
