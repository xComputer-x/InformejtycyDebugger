const socket = io({
    reconnection: true,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
    reconnectionAttempts: Infinity,
});

const ping_back_after = 3000; // Delay before ping after server's PONG reponse

var editor;
var last_highlighted;
var is_running = false;

// Enable debugging gui and disable pre-debugging gui
async function turn_gui_into_debugging() {
    await document.querySelectorAll("#panelGorny button").forEach((btn) => btn.disabled = false);
}

// Disable debugging gui and enable pre-debugging gui
async function turn_gui_back_from_debugging(timeout, runtime_error, runtime_error_details) {
    await document.querySelectorAll("#panelGorny button").forEach((btn) => btn.disabled = true);
    if (timeout) {
        document.getElementById("status").textContent = "Przekroczono limit czasu na komendę!";
    } else if (runtime_error) {
        document.getElementById("status").textContent = "Błąd wykonania w czasie wykonania!";
        document.getElementById("statusDetails").textContent = runtime_error_details;
    } else {
        document.getElementById("status").textContent = "Zakończono debugowanie!";
    }
}

// Function to sleep in async function
function sleep(time_in_miliseconds) {
    return new Promise((resolve) => setTimeout(resolve, time_in_miliseconds));
}

async function highlightLine(lineNumber) {
    if (last_highlighted) {
        editor.removeLineClass(last_highlighted, "wrap", "highlighted-line");
    }
    editor.addLineClass(lineNumber-1, "wrap", "highlighted-line");
    last_highlighted = lineNumber-1;
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

    if (!is_running) return;

    await sleep(ping_back_after);

    console.log("Now we ping back");
    socket.emit("ping", {authorization: auth});
})

// After some action receive debugging information
socket.on("debug_data", async (data) => {
    console.log("Server responded! Status:", data.status);
    console.log(data);
    highlightLine(data.line)

    is_running = data.is_running;

    if (!is_running) {
        await turn_gui_back_from_debugging(data.timeout, data.runtime_error, data.runtime_error_details);
    } else {
        document.getElementById("variablesInfo").textContent = "";

        data.local_variables.forEach(element => {
            document.getElementById("variablesInfo").textContent += JSON.stringify(element, null, 2) + "\n";
        });
    }
})

// this thing below was written by chatgpt
// beginregion
document.addEventListener("DOMContentLoaded", function () {
    editor = CodeMirror.fromTextArea(document.getElementById("cppEditor"), {
        mode: "text/x-c++src", // C++ syntax highlighting
        theme: "monokai",      // Editor theme
        lineNumbers: true,     // Show line numbers
        tabSize: 4,            // Set tab width
        indentWithTabs: true,  // Use tabs instead of spaces
        smartIndent: true,     // Auto-indent new lines
        matchBrackets: true,   // Highlight matching brackets
        autoCloseBrackets: true, // Automatically close brackets
    });
});
// endregion

// Listen for stopping
document.getElementById("zakonczDebugowanie").addEventListener("click", function stop_debugging() {
    socket.emit("stop", {authorization: authorization});
})

// Start of debugging
document.getElementById("debugStart").addEventListener("click", function start_debugging() {
    document.getElementById("status").textContent = "Wysłano prośbę o rozpoczęcie debugowania";
    document.getElementById("statusDetails").textContent = "";

    socket.emit("start_debugging", {code: editor.getValue(), input: ""});
})

// Listen for stepping
document.getElementById("krokDoPrzodu").addEventListener("click", function step_forward() {
    socket.emit("step", {authorization: authorization});
})

turn_gui_back_from_debugging()
