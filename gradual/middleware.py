import json

from hug.middleware import LogMiddleware


class LogMiddleware(LogMiddleware):
    def _generate_combined_log(self, request, response):
        info = super()._generate_combined_log(request, response)
        data = json.dumps(json.loads(response.data.decode('utf-8')), indent=4)
        return f'{info}\n{data}'
