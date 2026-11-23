let state = {
    inventory: [],
    transactions: [],
    reservations: [],
    users: [],
    stats: {}
};

const $ = id => document.getElementById(id);

const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
}[c]));

const itemById = id => state.inventory.find(i => i.Item_ID === id);

function toast(msg) {
    const el = $("toast");
    if (!el) return;

    el.textContent = msg;
    el.classList.add("show");

    setTimeout(() => el.classList.remove("show"), 3200);
}

function openModal(id) {
    $(id)?.classList.add("show");
}

function closeModal(id) {
    $(id)?.classList.remove("show");
}


// ===== NAVIGATION =====

function switchView(view) {
    const targetView = $(view + "-view");

    if (!targetView) {
        console.error("Dashboard view not found:", view);
        return;
    }

    document.querySelectorAll(".view").forEach(v => {
        v.classList.remove("active");
    });

    targetView.classList.add("active");

    // Only actual navigation buttons should be selected.
    document.querySelectorAll(".nav-link[data-view]").forEach(b => {
        b.classList.toggle("active", b.dataset.view === view);
    });

    $("crumb-name").textContent =
        view.charAt(0).toUpperCase() + view.slice(1);

    const titles = {
        overview: 'Good afternoon<span class="accent">.</span>',
        inventory: 'Equipment inventory<span class="accent">.</span>',
        borrowings: 'Borrowing records<span class="accent">.</span>',
        reservations: 'Reservation queue<span class="accent">.</span>',
        users: 'User management<span class="accent">.</span>'
    };

    $("page-title").innerHTML = titles[view] || view;
}

// FIX: Exclude Logout and other buttons without data-view.
document.querySelectorAll(".nav-link[data-view]").forEach(b => {
    b.addEventListener("click", () => switchView(b.dataset.view));
});


// ===== API CONNECTION =====

async function api(path, opts = {}) {
    const r = await fetch(path, {
        headers: {
            "Content-Type": "application/json",
            ...(opts.headers || {})
        },
        ...opts
    });

    const data = await r.json();

    if (!r.ok) {
        throw new Error(data.error || "Something went wrong");
    }

    return data;
}


// ===== LOAD DASHBOARD DATA =====

async function loadData() {
    const start = performance.now();

    try {
        state = await api("/api/bootstrap");

        console.log(
            "Dashboard data loading:",
            ((performance.now() - start) / 1000).toFixed(3),
            "seconds"
        );

        renderAll();

        if ($("updated-at")) {
            $("updated-at").textContent = "Updated just now";
        }

        return true;

    } catch (e) {
        toast("Cannot load data: " + e.message);
        return false;
    }
}


// ===== RENDER ALL =====

function renderAll() {
    const s = state.stats || {};

    $("stat-items").textContent = s.items ?? 0;
    $("stat-available").textContent = s.available ?? 0;
    $("stat-active").textContent = s.active_loans ?? 0;
    $("stat-overdue").textContent = s.overdue ?? 0;

    renderFeatured();
    renderInventory();
    renderBorrowings();
    renderReservations();
    renderActivity();
    renderUsers();
    populateSelects();
}


// ===== FEATURED INVENTORY =====

function renderFeatured() {
    const items = state.inventory.slice(0, 4);

    $("featured-inventory").innerHTML = items.length
        ? items.map(i => `
            <div class="inventory-row">
                <div class="item-symbol">▦</div>
                <div class="item-main">
                    <b>${esc(i.Item_Name)}</b>
                    <small>${esc(i.Item_ID)} · ${esc(i.Category)}</small>
                </div>
                <div class="availability">
                    <b>${esc(i.Available_Quantity)} / ${esc(i.Total_Quantity)}</b>
                    <small>units available</small>
                </div>
            </div>
        `).join("")
        : '<div class="empty-state">No inventory has been added yet.</div>';
}


// ===== INVENTORY =====

function renderInventory() {
    const q = ($("inventory-search")?.value || "").toLowerCase();

    const rows = state.inventory.filter(i =>
        [i.Item_Name, i.Item_ID, i.Category]
            .join(" ")
            .toLowerCase()
            .includes(q)
    );

    $("inventory-count").textContent = rows.length + " items";

    $("inventory-table").innerHTML = rows.length
        ? rows.map(i => `
            <tr>
                <td>
                    <div class="equipment-cell">
                        <div class="item-symbol">▦</div>
                        <div>
                            <b>${esc(i.Item_Name)}</b><br>
                            <small>${esc(i.Item_ID)}</small>
                        </div>
                    </div>
                </td>
                <td>${esc(i.Category)}</td>
                <td><b>${esc(i.Available_Quantity)}</b> / ${esc(i.Total_Quantity)}</td>
                <td>${esc(i.Borrowed_Quantity)}</td>
                <td>${esc(i.Condition)}</td>
                <td>
                    <span class="status ${i.Item_Status !== "Available" ? "warn" : ""}">
                        ${esc(i.Item_Status)}
                    </span>
                </td>
            </tr>
        `).join("")
        : '<tr><td colspan="6" class="empty-state">No matching equipment found.</td></tr>';
}


// ===== BORROWING RECORDS =====

function renderBorrowings() {
    const q = ($("borrowing-search")?.value || "").toLowerCase();

    const rows = [...state.transactions]
        .reverse()
        .filter(t =>
            [t.Transaction_ID, t.Item_ID, t.User_ID]
                .join(" ")
                .toLowerCase()
                .includes(q)
        );

    $("borrowing-table").innerHTML = rows.length
        ? rows.map(t => {
            const item = itemById(t.Item_ID);

            const overdue =
                t.Transaction_Status === "Borrowed" &&
                t.Due_Date < new Date().toISOString().slice(0, 10);

            return `
                <tr>
                    <td><b>${esc(t.Transaction_ID)}</b></td>
                    <td>${esc(t.User_ID)}</td>
                    <td>${esc(item?.Item_Name || t.Item_ID)}</td>
                    <td>${esc(t.Issue_Date)}</td>
                    <td>${esc(t.Due_Date)}</td>
                    <td>
                        <span class="status ${overdue || t.Transaction_Status.includes("Inspection") ? "warn" : ""}">
                            ${overdue ? "Overdue" : esc(t.Transaction_Status)}
                        </span>
                    </td>
                </tr>
            `;
        }).join("")
        : '<tr><td colspan="6" class="empty-state">No borrowing records yet.</td></tr>';
}


// ===== RESERVATIONS =====

function renderReservations() {
    $("reservation-table").innerHTML = state.reservations.length
        ? [...state.reservations].reverse().map(r => `
            <tr>
                <td><b>${esc(r.Reservation_ID)}</b></td>
                <td>${esc(r.User_ID)}</td>
                <td>${esc(r.Item_ID)}</td>
                <td>${esc(r.Request_Date)}</td>
                <td>#${esc(r.Priority_Number)}</td>
                <td>
                    <span class="status neutral">${esc(r.Reservation_Status)}</span>
                </td>
            </tr>
        `).join("")
        : '<tr><td colspan="6" class="empty-state">No reservation requests yet.</td></tr>';
}


// ===== RECENT ACTIVITY =====

function renderActivity() {
    const rows = [...state.transactions].slice(-5).reverse();

    $("recent-activity").innerHTML = rows.length
        ? rows.map(t => `
            <div class="activity-row">
                <div class="activity-mark">${t.Return_Date ? "↩" : "↗"}</div>
                <div class="activity-copy">
                    <b>${esc(t.User_ID)}</b>
                    ${t.Return_Date ? "returned" : "borrowed"}
                    <b>${esc(itemById(t.Item_ID)?.Item_Name || t.Item_ID)}</b>
                    <small>
                        ${esc(t.Return_Date || t.Issue_Date)}
                        · ${esc(t.Transaction_Status)}
                    </small>
                </div>
            </div>
        `).join("")
        : '<div class="empty-state">Activity will appear here after the first checkout.</div>';
}


// ===== REGISTERED USERS =====

function renderUsers() {
    const tbody = $("users-table");

    if (!tbody) return;

    if (!state.users || state.users.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5">No registered users found.</td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = state.users.map(user => `
        <tr>
            <td>${esc(user.Full_Name)}</td>
            <td>${esc(user.USN_or_Staff_ID)}</td>
            <td>${esc(user.Email)}</td>
            <td>${esc(user.Role)}</td>
            <td>${esc(user.Account_Status)}</td>
        </tr>
    `).join("");
}


// ===== POPULATE ITEM DROPDOWNS =====

function populateSelects() {
    ["borrow-item", "reserve-item"].forEach(id => {
        const element = $(id);

        if (!element) return;

        element.innerHTML = state.inventory.map(i => `
            <option value="${esc(i.Item_ID)}">
                ${esc(i.Item_Name)} · ${esc(i.Available_Quantity)} available
            </option>
        `).join("");
    });
}


// ===== FORM HELPER =====

function formObject(form) {
    return Object.fromEntries(new FormData(form).entries());
}


// ===== BORROW EQUIPMENT =====

$("borrow-form").addEventListener("submit", async e => {
    e.preventDefault();

    try {
        const d = formObject(e.target);
        d.quantity = Number(d.quantity);

        const r = await api("/api/borrow", {
            method: "POST",
            body: JSON.stringify(d)
        });

        toast(r.message + " ID: " + r.transaction_id);

        e.target.reset();
        closeModal("borrow-modal");

        await loadData();

    } catch (err) {
        toast(err.message);
    }
});


// ===== RETURN EQUIPMENT =====

$("return-form").addEventListener("submit", async e => {
    e.preventDefault();

    try {
        const r = await api("/api/return", {
            method: "POST",
            body: JSON.stringify(formObject(e.target))
        });

        toast(r.message);

        e.target.reset();
        closeModal("return-modal");

        await loadData();

    } catch (err) {
        toast(err.message);
    }
});


// ===== RESERVE EQUIPMENT =====

$("reserve-form").addEventListener("submit", async e => {
    e.preventDefault();

    try {
        const r = await api("/api/reservations", {
            method: "POST",
            body: JSON.stringify(formObject(e.target))
        });

        toast(r.message);

        e.target.reset();
        closeModal("reserve-modal");

        await loadData();

    } catch (err) {
        toast(err.message);
    }
});


// ===== MODAL HANDLING =====

document.querySelectorAll(".modal-backdrop").forEach(m => {
    m.addEventListener("click", e => {
        if (e.target === m) {
            m.classList.remove("show");
        }
    });
});


// ===== DUE DATE DEFAULT =====

const today = new Date();

$("due-date").min = today.toISOString().slice(0, 10);

const due = new Date();
due.setDate(due.getDate() + 3);

$("due-date").value = due.toISOString().slice(0, 10);


// ===== LOGIN AND SESSION MANAGEMENT =====

const loginScreen = $("login-screen");
const appShell = document.querySelector(".app-shell");

// Hide dashboard until login is verified.
appShell.style.display = "none";


function showLogin() {
    loginScreen.classList.add("active");
    appShell.style.display = "none";
}


function showDashboard() {
    loginScreen.classList.remove("active");
    appShell.style.display = "";
}


// ===== LOGIN FORM =====

$("login-form").addEventListener("submit", async function(e) {
    e.preventDefault();

    const errorBox = $("login-error");
    errorBox.classList.remove("show");

    try {
        const result = await api("/api/login", {
            method: "POST",
            body: JSON.stringify({
                username: $("login-username").value.trim(),
                password: $("login-password").value
            })
        });

        // Check the role returned by Flask
        const role = (result.role || "").trim().toLowerCase();

        // Show or hide Manage Users
        const manageUsersButton = document.querySelector(
            '[data-view="users"]'
        );

        if (manageUsersButton) {
            manageUsersButton.style.display =
                role === "admin" ? "" : "none";
        }

        showDashboard();

        const loaded = await loadData();

        if (!loaded) {
            showLogin();
            return;
        }

        toast("Welcome, " + result.username);

    } catch (error) {
        errorBox.textContent = error.message;
        errorBox.classList.add("show");
    }
});


// ===== CHECK EXISTING SESSION =====

async function initializeAuth() {
    try {
        const result = await api("/api/session");

        if (result.logged_in) {
            showDashboard();
            const loaded = await loadData();

            if (!loaded) {
                showLogin();
            }

        } else {
            showLogin();
        }

    } catch (error) {
        showLogin();
    }
}

initializeAuth();


// ===== LOGOUT =====

$("logout-button").addEventListener("click", async function() {
    try {
        await api("/api/logout", {
            method: "POST"
        });

        showLogin();

        $("login-form").reset();

        toast("Logged out successfully");

    } catch (error) {
        toast("Logout failed: " + error.message);
    }
});


// ===== CREATE USER ACCOUNT =====

$("user-form").addEventListener("submit", async function(e) {
    e.preventDefault();

    const formData = new FormData(this);

    const userData = {
        full_name: formData.get("full_name"),
        user_code: formData.get("user_code"),
        email: formData.get("email"),
        role: formData.get("role"),
        department: formData.get("department")
    };

    try {
        const result = await api("/api/admin/users", {
            method: "POST",
            body: JSON.stringify(userData)
        });

        alert(
            "Account created successfully!\n\n" +
            "Username: " + result.username +
            "\nTemporary Password: " + result.temporary_password
        );

        closeModal("user-modal");

        this.reset();

        await loadData();

    } catch (error) {
        alert(error.message);
    }
});