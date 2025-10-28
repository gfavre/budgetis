class StripServerHeaderMiddleware:
    """
    Removes the Server header from all HTTP responses.
    """

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        def custom_start_response(status, response_headers, exc_info=None):
            filtered = [(k, v) for k, v in response_headers if k.lower() != "server"]
            return start_response(status, filtered, exc_info)

        return self.app(environ, custom_start_response)
