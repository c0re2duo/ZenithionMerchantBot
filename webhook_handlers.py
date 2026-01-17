import logging

from aiohttp import web

from config import config
from handlers import new_deposit_notify


async def handle_payment_webhook(request):
    try:
        data = await request.json()

        api_key = request.headers.get("X-API-Key")

        if not api_key or (api_key and api_key != config.webhooks_api_key):
            return web.Response(text="Unauthorized", status=403)

        logging.info(f"New webhook.")

        if data.get("message", "") == "new_deposit":
            await new_deposit_notify(data['address'], data['amount'], data['new_status'], data['merchant_api_token'])

        return web.Response(text="Success", status=200)
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return web.Response(text="Error", status=400)