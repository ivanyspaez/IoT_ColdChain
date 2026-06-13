from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from datetime import datetime

latest_data = {
    "device_id": "Sin datos",
    "temperature": 0,
    "humidity": 0,
    "battery": 0,
    "status": "N/A"
}

history = []


class TelemetryHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        if self.path == "/api/latest":

            self.send_response(200)
            self.send_header(
                "Content-Type",
                "application/json; charset=utf-8"
            )
            self.end_headers()

            self.wfile.write(
                json.dumps(latest_data).encode("utf-8")
            )
            return

        if self.path == "/api/history":

            self.send_response(200)
            self.send_header(
                "Content-Type",
                "application/json; charset=utf-8"
            )
            self.end_headers()

            self.wfile.write(
                json.dumps(history).encode("utf-8")
            )
            return

        html = """
<!DOCTYPE html>
<html>
<head>

<meta charset="UTF-8">

<title>ColdChain Dashboard</title>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<style>

body{
    font-family: Arial;
    background:#f0f2f5;
    margin:20px;
}

h1{
    color:#1d3557;
}

.card{
    background:white;
    padding:20px;
    border-radius:10px;
    margin-bottom:20px;
    box-shadow:0px 0px 10px rgba(0,0,0,0.15);
}

.grid{
    display:grid;
    grid-template-columns:repeat(2,1fr);
    gap:20px;
}

.value{
    font-size:28px;
    font-weight:bold;
}

table{
    width:100%;
    border-collapse:collapse;
}

th,td{
    padding:10px;
    border-bottom:1px solid #ddd;
}

</style>

</head>

<body>

<h1>ColdChain Dashboard</h1>

<div class="grid">

<div class="card">
<h3>Temperatura Actual</h3>
<div class="value" id="temp">--</div>
</div>

<div class="card">
<h3>Humedad Actual</h3>
<div class="value" id="hum">--</div>
</div>

</div>

<div class="card">

<canvas id="tempChart"></canvas>

</div>

<div class="card">

<canvas id="humChart"></canvas>

</div>

<div class="card">

<h3>Últimos Registros</h3>

<table>

<thead>
<tr>
<th>Hora</th>
<th>Temp</th>
<th>Humedad</th>
</tr>
</thead>

<tbody id="historyTable">

</tbody>

</table>

</div>

<script>

let tempChart;
let humChart;

async function updateDashboard(){

    const latest =
        await fetch('/api/latest')
        .then(r=>r.json());

    document.getElementById("temp").innerHTML =
        latest.temperature + " °C";

    document.getElementById("hum").innerHTML =
        latest.humidity + " %";

    const history =
        await fetch('/api/history')
        .then(r=>r.json());

    const labels =
        history.map(x=>x.time);

    const temperatures =
        history.map(x=>x.temperature);

    const humidities =
        history.map(x=>x.humidity);

    if(tempChart){
        tempChart.destroy();
    }

    if(humChart){
        humChart.destroy();
    }

    tempChart = new Chart(
        document.getElementById('tempChart'),
        {
            type:'line',
            data:{
                labels:labels,
                datasets:[{
                    label:'Temperatura °C',
                    data:temperatures
                }]
            }
        }
    );

    humChart = new Chart(
        document.getElementById('humChart'),
        {
            type:'line',
            data:{
                labels:labels,
                datasets:[{
                    label:'Humedad %',
                    data:humidities
                }]
            }
        }
    );

    let table = "";

    history
    .slice()
    .reverse()
    .forEach(row=>{

        table += `
        <tr>
            <td>${row.time}</td>
            <td>${row.temperature}</td>
            <td>${row.humidity}</td>
        </tr>
        `;

    });

    document.getElementById(
        "historyTable"
    ).innerHTML = table;
}

updateDashboard();

setInterval(
    updateDashboard,
    5000
);

</script>

</body>
</html>
"""

        self.send_response(200)
        self.send_header(
            "Content-Type",
            "text/html; charset=utf-8"
        )
        self.end_headers()

        self.wfile.write(
            html.encode("utf-8")
        )

    def do_POST(self):

        global latest_data
        global history

        if self.path != "/telemetry":

            self.send_response(404)
            self.end_headers()
            return

        content_length = int(
            self.headers.get(
                "Content-Length",
                0
            )
        )

        body = self.rfile.read(
            content_length
        )

        data = json.loads(
            body.decode()
        )

        latest_data = data

        history.append({
            "time":
                datetime.now().strftime(
                    "%H:%M:%S"
                ),
            "temperature":
                data["temperature"],
            "humidity":
                data["humidity"]
        })

        if len(history) > 100:
            history.pop(0)

        print("\n==================================================")
        print("PAQUETE RECIBIDO")
        print("==================================================")
        print(
            json.dumps(
                data,
                indent=4
            )
        )

        self.send_response(200)

        self.send_header(
            "Content-Type",
            "application/json"
        )

        self.end_headers()

        self.wfile.write(
            json.dumps({
                "ok": True,
                "message":
                    "Telemetry received"
            }).encode()
        )


if __name__ == "__main__":

    server = HTTPServer(
        ("0.0.0.0", 8000),
        TelemetryHandler
    )

    print("\n==================================================")
    print("COLDCHAIN DASHBOARD")
    print("==================================================")
    print("http://localhost:8000")
    print("==================================================\n")

    server.serve_forever()