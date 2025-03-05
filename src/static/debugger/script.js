const socket = io({
    reconnection: true,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
    reconnectionAttempts: Infinity,
});

const ping_back_after = 3000; // Delay before ping after server's PONG reponse

// Enable debugging gui and disable pre-debugging gui
async function turn_gui_into_debugging() {

    await document.querySelectorAll("#panelGorny button").forEach((btn) => btn.disabled = false);
}

// Disable debugging gui and enable pre-debugging gui
async function turn_gui_back_from_debugging() {

    await document.querySelectorAll("#panelGorny button").forEach((btn) => btn.disabled = true);
}

// Function to sleep in async function
function sleep(time_in_miliseconds) {
    return new Promise((resolve) => setTimeout(resolve, time_in_miliseconds));
}

function highlightLine(lineNumber) {
    const elements = document.querySelectorAll('.linemark');

    // Loop through each element
    elements.forEach(element => {
        // Replace the element with its text content
        element.replaceWith(element.textContent);
    });

    const preElement = document.getElementById("debugCode");
    if (!preElement) return;
    
    const lines = preElement.innerHTML.split('\n');
    if (lineNumber < 1 || lineNumber > lines.length) return;
    
    lines[lineNumber - 1] = `<mark class="linemark">${lines[lineNumber - 1]}</mark>`;
    preElement.innerHTML = lines.join('\n');
}


// Connection debuginfo
socket.on("connect", () => {
    console.log("Socket is connected!");
})

// Deconnection debuginfo
socket.on("disconnect", () => {
    console.log("Socket is disconnected! Attempting to reconnect...");
})

// When server responds after start_debugging
socket.on("started_debugging", (data) => {
    if (data.compilation_error) {
        turn_gui_back_from_debugging();
        document.getElementById("status").textContent = "błąd kompilacji! Przerywanie debugowania! ";
        document.getElementById("statusDetails").textContent = data.compilation_error_details;
    } else {
        turn_gui_into_debugging();
        document.getElementById("status").textContent = "sukces. Rozpoczęto debugowanie!";
        document.getElementById("statusDetails").textContent = "";

        auth = data.authorization;
        authorization = data.authorization;
        console.log("Started debugging, auth:", auth);

        socket.emit("ping", {authorization: auth});
    }
})

// When server responds on pinging
socket.on("pong", async (data) => {
    console.log("Server responded! Status:", data.status);

    await sleep(ping_back_after);

    console.log("Now we ping back");
    socket.emit("ping", {authorization: auth});
})

// After some action receive debugging information
socket.on("debug_data", async (data) => {
    console.log("Server responded! Status:", data.status);
    console.log(data);
    highlightLine(data.line)
})

// Start of debugging
document.getElementById("debugStart").addEventListener("click", function start_debugging() {
    socket.emit("start_debugging", {code: document.querySelector('#debugCode').innerText, input: ""});
})

// Listen for stepping
document.getElementById("krokDoPrzodu").addEventListener("click", function step_forward() {
    socket.emit("step", {authorization: authorization});
})

turn_gui_back_from_debugging()
