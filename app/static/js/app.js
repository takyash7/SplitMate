document.addEventListener("DOMContentLoaded", () => {

const typeSelect = document.getElementById("split-type");
const inputsWrap = document.getElementById("split-inputs");
const fields = document.getElementById("split-fields");
const help = document.getElementById("split-help");
const form = document.getElementById("expense-form");

// Check required HTML elements
if (!typeSelect || !form || !inputsWrap || !fields || !help) {
    console.error("Expense form elements are missing.");
    return;
}

console.log("Expense form JavaScript loaded.");

function renderSplitFields() {

    const type = typeSelect.value;

    const selected = [
        ...form.querySelectorAll(
            'input[name="participants"]:checked'
        )
    ];

    inputsWrap.hidden = type === "equal";

    fields.innerHTML = "";

    if (type === "equal") {
        return;
    }

    const labels = {
        exact: "Amount (₹)",
        percentage: "Percentage (%)",
        shares: "Share weight"
    };

    help.textContent =
        type === "exact"
            ? "All exact amounts must add up to the full expense amount."
            : type === "percentage"
                ? "Percentages must add up to exactly 100."
                : "Use relative weights, for example 1, 2 and 1.";

    selected.forEach((checkbox) => {

        const id = checkbox.value;
        const name = checkbox.dataset.name || "Member";

        const col = document.createElement("div");
        col.className = "col-md-6";

        const label = document.createElement("label");
        label.className = "form-label small";
        label.textContent = `${name} - ${labels[type]}`;

        const input = document.createElement("input");

        input.className = "form-control";
        input.type = "number";
        input.step = "0.01";
        input.min = "0";
        input.name = `share_${id}`;
        input.required = true;

        if (type === "percentage") {
            input.value = (
                100 / Math.max(selected.length, 1)
            ).toFixed(2);

        } else if (type === "shares") {
            input.value = "1";

        } else {
            input.value = "";
        }

        label.appendChild(input);
        col.appendChild(label);
        fields.appendChild(col);

    });
}

// Split method change
typeSelect.addEventListener("change", renderSplitFields);

// Participant selection change
form.querySelectorAll(
  'input[name="participants"]'
).forEach((checkbox) => {
    checkbox.addEventListener("change", renderSplitFields);
});

// Initial rendering
renderSplitFields();

// Form submission debugging
form.addEventListener("submit", () => {
    console.log("FORM SUBMIT EVENT FIRED");
    console.log("Action:", form.action);
    console.log("Method:", form.method);
});

});