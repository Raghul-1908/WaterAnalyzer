document.getElementById("runBtn").addEventListener("click", async () => {

    document.getElementById("allocations").innerHTML = "Processing...";
    document.getElementById("anomalies").innerHTML = "";
    document.getElementById("report").innerHTML = "";

    const response = await fetch("/run");
    const data = await response.json();

    // Format allocations as table
    let table = "<table><tr><th>Sector</th><th>Allocated (ML)</th></tr>";

    for (let key in data.allocations) {
        table += `<tr><td>${key}</td><td>${data.allocations[key]}</td></tr>`;
    }

    table += "</table>";
    document.getElementById("allocations").innerHTML = table;

    // Format anomalies
    document.getElementById("anomalies").innerHTML =
        data.anomalies.length
            ? "<ul>" + data.anomalies.map(a => `<li>${a}</li>`).join("") + "</ul>"
            : "No anomalies detected.";

    // Clean markdown-like formatting
    let cleanReport = data.report.replace(/\*\*/g, "");
    document.getElementById("report").innerText = cleanReport;
});
