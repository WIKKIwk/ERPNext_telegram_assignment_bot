redis_cache: redis-server config/redis_cache.conf
redis_queue: redis-server config/redis_queue.conf
web: ./env/bin/bench serve --port 8000
socketio: node apps/frappe/socketio.js
watch: ./env/bin/bench watch
schedule: ./env/bin/bench schedule
worker: ./env/bin/bench worker 1>> logs/worker.log 2>> logs/worker.error.log
