from flask import Flask, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix
from urllib.parse import urlparse

PORT = 5055

app = Flask(__name__, static_folder='./static')
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

@app.route('/')
def index():
    host = urlparse(request.url_root).hostname
    return render_template('web_kovesd.html', host=host)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)
