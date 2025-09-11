from portkey_ai import PORTKEY_GATEWAY_URL, createHeaders
from src.config.settings import settings


def create_port_key_headers(trace_id):
    portkey_headers = createHeaders(
                api_key=settings.PORTKEY_API_KEY, provider="azure-openai", trace_id=trace_id
            )

    portkey_gateway_url = PORTKEY_GATEWAY_URL
    return portkey_headers,portkey_gateway_url