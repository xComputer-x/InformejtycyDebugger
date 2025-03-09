const socket = io({
    reconnection: true,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
    reconnectionAttempts: Infinity,
});

const ping_back_after = 3000; // Delay before ping after server's PONG reponse

var editor; // codemirror variable
var last_highlighted;
var is_running = false;

// Enable debugging gui and disable pre-debugging gui
async function turn_gui_into_debugging() {
    document.querySelectorAll("#panelGorny button").forEach((btn) => btn.disabled = false);
    document.getElementById("debugStart").disabled = true;
}

// Disable debugging gui and enable pre-debugging gui
async function turn_gui_back_from_debugging(timeout, runtime_error, runtime_error_details) {
    document.querySelectorAll("#panelGorny button").forEach((btn) => btn.disabled = true);
    document.getElementById("debugStart").disabled = false;
    if (timeout) {
        document.getElementById("status").textContent = "Przekroczono limit czasu na komendę!";
    } else if (runtime_error) {
        document.getElementById("status").textContent = "Błąd w czasie wykonania programu!";
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
socket.on("started_debugging", async (data) => {
    if (data.compilation_error) {
        turn_gui_back_from_debugging();
        document.getElementById("status").textContent = "błąd kompilacji! Przerywanie debugowania! ";
        document.getElementById("statusDetails").textContent = data.compilation_error_details;
    } else {
        await turn_gui_into_debugging();
        document.getElementById("status").textContent = "Sukces! Serwer uruchomił debugger. Aby rozpocząć debugowanie, wybierz punkty przerwania kodu (breakpointy), a następnie naciśnij przycisk \"Uruchom\"";
        document.getElementById("statusDetails").textContent = "";

        auth = data.authorization;
        authorization = data.authorization;
        console.log("Started debugging, auth:", auth);

        await socket.emit("ping", {authorization: auth});
    }
})

// When server responds on pinging
socket.on("pong", async (data) => {
    console.log("Server responded! Status:", data.status);

    if (!is_running) return;

    await sleep(ping_back_after);

    console.log("Now we ping back");
    await socket.emit("ping", {authorization: auth});
})

// After some action receive debugging information
socket.on("debug_data", async (data) => {
    console.log("Server responded! Status:", data.status);
    console.log(data);

    if (data.status != "ok") {
        console.log("Something went wrong... Status is not ok!");
        return;
    }

    highlightLine(data.line)

    is_running = data.is_running;

    if (!is_running) {
        await turn_gui_back_from_debugging(data.timeout, data.runtime_error, data.runtime_error_details);

        const lines = editor.lineCount();
        for (var i=0; i<lines; i++) {
            await editor.removeLineClass(i, "wrap", "highlighted-line");
        }
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

// Starts of debugging
document.getElementById("debugStart").addEventListener("click", async () => {
    document.getElementById("status").textContent = "Wysłano prośbę o rozpoczęcie debugowania";
    document.getElementById("statusDetails").textContent = "";

    await socket.emit("start_debugging", {code: editor.getValue(), input: ""});
})

//
// "add_breakpoints" and "remove_breakpoints" should be arrays of integers
//

// Listens for stepping
document.getElementById("krokDoPrzodu").addEventListener("click", async () => {
    await socket.emit("step", {authorization: authorization, add_breakpoints: [], remove_breakpoints: [8]});
})

// Listens for running
document.getElementById("uruchomKod").addEventListener("click", async () => {
    await socket.emit("run", {authorization: authorization, add_breakpoints: [5, 8], remove_breakpoints: []});
})

// Listens for continuing
document.getElementById("kontynuujWykonanie").addEventListener("click", async () => {
    await socket.emit("continue", {authorization: authorization, add_breakpoints: [], remove_breakpoints: []});
})

// Listen for finishing
document.getElementById("zakonczFunkcje").addEventListener("click", async () => {
    await socket.emit("finish", {authorization: authorization, add_breakpoints: [], remove_breakpoints: []});
})

// Listen sfor stopping
document.getElementById("zakonczDebugowanie").addEventListener("click", async () => {
    await socket.emit("stop", {authorization: authorization});
})