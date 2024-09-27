from flask import Flask, render_template, request
from urllib.parse import urlparse

app = Flask(__name__)

@app.route('/')
def index():
    host = urlparse(request.url_root).hostname
    return render_template('web_kovesd.html', host=host)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5055)
