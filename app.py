from flask import Flask, render_template, jsonify
import threading
from main import SmartWaterController
import logging

# Initialize Flask
app = Flask(__name__)

# Initialize Controller
# We start it in a separate thread so Flask can run
controller = SmartWaterController(dry_run=False)

def run_controller():
    controller.run()

# Start Controller Thread
t = threading.Thread(target=run_controller, daemon=True)
t.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    state = controller.get_state()
    return jsonify(state)

if __name__ == "__main__":
    # Host 0.0.0.0 allows access from local network if needed
    app.run(host='0.0.0.0', port=5000, debug=False)
