bind = "10.233.1.13:8000"
workers = 8
threads = 1
worker_class = "sync"
accesslog = "/home/f/log/gunicorn/access.log"
errorlog = "/home/f/log/gunicorn/error.log"
loglevel = "info"