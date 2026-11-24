
// =========================================================
// BORROW BOARD - MAIN JAVASCRIPT
// =========================================================

let state = {
    inventory: [],
    transactions: [],
    reservations: [],
    users: [],
    stats: {},
    currentUser: {
        user_id: "",
        role: "",
        username: ""
    }
};


// =========================================================
// BASIC HELPERS
// =========================================================

const $ = id => document.getElementById(id);

const esc = value =>
    String(value ?? "").replace(/[&<>"']/g, character => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
    }[character]));

function normalize(value) {
    return String(value ?? "").trim().toLowerCase();
}

function itemById(id) {
    return state.inventory.find(
        item => normalize(item.Item_ID) === normalize(id)
    );
}

function userByCode(code) {
    return state.users.find(user =>
        normalize(user.USN_or_Staff_ID) === normalize(code)
    );
}

function toast(message) {
    const element = $("toast");

    if (!element) {
        alert(message);
        return;
    }

    element.textContent = message;
    element.classList.add("show");

    setTimeout(() => {
        element.classList.remove("show");
    }, 3200);
}

function openModal(id) {
    $(id)?.classList.add("show");
}

function closeModal(id) {
    $(id)?.classList.remove("show");
}


// =========================================================
// ROLE HELPERS
// =========================================================

function getRole() {
    return normalize(state.currentUser.role);
}

function isAdmin() {
    return getRole() === "admin";
}

function isStaff() {
    return getRole() === "staff";
}

function isStudent() {
    return getRole() === "student";
}


// =========================================================
// NAVIGATION
// =========================================================

function switchView(view) {
    if (view === "users" && !isAdmin()) {
        toast("You do not have permission to access this page.");
        return;
    }

    const targetView = $(view + "-view");

    if (!targetView) {
        console.error("Dashboard view not found:", view);
        return;
    }

    document.querySelectorAll(".view").forEach(element => {
        element.classList.remove("active");
    });

    targetView.classList.add("active");

    document.querySelectorAll(".nav-link[data-view]").forEach(button => {
        button.classList.toggle(
            "active",
            button.dataset.view === view
        );
    });

    const breadcrumb = $("crumb-name");

    if (breadcrumb) {
        breadcrumb.textContent =
            view.charAt(0).toUpperCase() + view.slice(1);
    }

    const titles = {
        overview: 'Good afternoon<span class="accent">.</span>',
        inventory: 'Equipment inventory<span class="accent">.</span>',
        borrowings: 'Borrowing records<span class="accent">.</span>',
        reservations: 'Reservation queue<span class="accent">.</span>',
        users: 'User management<span class="accent">.</span>'
    };

    const pageTitle = $("page-title");

    if (pageTitle) {
        pageTitle.innerHTML = titles[view] || view;
    }
}

document.querySelectorAll(".nav-link[data-view]").forEach(button => {
    button.addEventListener("click", () => {
        switchView(button.dataset.view);
    });
});


// =========================================================
// API
// =========================================================

async function api(path, options = {}) {
    const requestOptions = {
        ...options,
        headers: {
            ...(options.body ? {
                "Content-Type": "application/json"
            } : {}),
            ...(options.headers || {})
        }
    };

    const response = await fetch(path, requestOptions);

    let data = {};

    try {
        data = await response.json();
    } catch (error) {
        if (!response.ok) {
            throw new Error(`Server error (${response.status})`);
        }
    }

    if (!response.ok) {
        throw new Error(
            data.error || `Request failed (${response.status})`
        );
    }

    return data;
}


// =========================================================
// ROLE-BASED UI VISIBILITY
// =========================================================

function updateRoleControls() {
    const role = getRole();

    // Users page is Admin only.
    const usersButton = document.querySelector(
        '[data-view="users"]'
    );

    if (usersButton) {
        usersButton.style.display =
            role === "admin" ? "" : "none";
    }

    const usersView = $("users-view");

    if (usersView && role !== "admin") {
        usersView.style.display = "none";
    }

    // Hide borrowing and return actions from Students.
    document.querySelectorAll(
        '[onclick*="borrow-modal"], [onclick*="return-modal"]'
    ).forEach(button => {
        button.style.display =
            role === "student" ? "none" : "";
    });

    // Hide user creation actions from Staff and Students.
    document.querySelectorAll(
        '[onclick*="user-modal"]'
    ).forEach(button => {
        button.style.display =
            role === "admin" ? "" : "none";
    });

    // Also hide buttons based on their visible labels.
    document.querySelectorAll("button").forEach(button => {
        const label = normalize(button.textContent);

        if (
            label.includes("new checkout") ||
            label.includes("record return")
        ) {
            button.style.display =
                role === "student" ? "none" : "";
        }

        if (
            label.includes("create user account")
        ) {
            button.style.display =
                role === "admin" ? "" : "none";
        }
    });

    // Students can request reservations.
    const reserveButtons = document.querySelectorAll(
        '[onclick*="reserve-modal"]'
    );

    reserveButtons.forEach(button => {
        button.style.display = "";
    });
}


// =========================================================
// LOAD DATA
// =========================================================

async function loadData() {
    const start = performance.now();

    try {
        const data = await api("/api/bootstrap");

        state = {
            ...state,

            inventory: Array.isArray(data.inventory)
                ? data.inventory
                : [],

            transactions: Array.isArray(data.transactions)
                ? data.transactions
                : [],

            reservations: Array.isArray(data.reservations)
                ? data.reservations
                : [],

            users: Array.isArray(data.users)
                ? data.users
                : [],

            stats: data.stats || {},

            currentUser: {
                user_id: data.current_user?.user_id ||
                    state.currentUser.user_id,

                username: data.current_user?.username ||
                    state.currentUser.username,

                role: data.current_user?.role ||
                    state.currentUser.role
            }
        };

        console.log(
            "Dashboard data loaded in:",
            ((performance.now() - start) / 1000).toFixed(3),
            "seconds"
        );

        updateRoleControls();
        renderAll();

        const updatedAt = $("updated-at");

        if (updatedAt) {
            updatedAt.textContent = "Updated just now";
        }

        return true;

    } catch (error) {
        console.error("LOAD DATA ERROR:", error);
        toast("Cannot load data: " + error.message);
        return false;
    }
}


// =========================================================
// RENDER EVERYTHING
// =========================================================

function renderAll() {
    const stats = state.stats || {};

    if ($("stat-items")) {
        $("stat-items").textContent = stats.items ?? 0;
    }

    if ($("stat-available")) {
        $("stat-available").textContent = stats.available ?? 0;
    }

    if ($("stat-active")) {
        $("stat-active").textContent = stats.active_loans ?? 0;
    }

    if ($("stat-overdue")) {
        $("stat-overdue").textContent = stats.overdue ?? 0;
    }

    renderFeatured();
    renderInventory();
    renderBorrowings();
    renderReservations();
    renderActivity();
    renderUsers();
    populateSelects();
}


// =========================================================
// FEATURED INVENTORY
// =========================================================

function renderFeatured() {
    const container = $("featured-inventory");

    if (!container) return;

    const items = state.inventory.slice(0, 4);

    if (!items.length) {
        container.innerHTML =
            '<div class="empty-state">No inventory has been added yet.</div>';
        return;
    }

    container.innerHTML = items.map(item => `
        <div class="inventory-row">
            <div class="item-symbol">▦</div>

            <div class="item-main">
                <b>${esc(item.Item_Name)}</b>
                <small>
                    ${esc(item.Item_ID)} · ${esc(item.Category)}
                </small>
            </div>

            <div class="availability">
                <b>
                    ${esc(item.Available_Quantity)}
                    /
                    ${esc(item.Total_Quantity)}
                </b>
                <small>units available</small>
            </div>
        </div>
    `).join("");
}


// =========================================================
// INVENTORY TABLE
// =========================================================

function renderInventory() {
    const table = $("inventory-table");

    if (!table) return;

    const search = normalize($("inventory-search")?.value);

    const rows = state.inventory.filter(item => {
        return [
            item.Item_Name,
            item.Item_ID,
            item.Category
        ].join(" ").toLowerCase().includes(search);
    });

    if ($("inventory-count")) {
        $("inventory-count").textContent = rows.length + " items";
    }

    if (!rows.length) {
        table.innerHTML = `
            <tr>
                <td colspan="6" class="empty-state">
                    No matching equipment found.
                </td>
            </tr>
        `;
        return;
    }

    table.innerHTML = rows.map(item => `
        <tr>
            <td>
                <div class="equipment-cell">
                    <div class="item-symbol">▦</div>
                    <div>
                        <b>${esc(item.Item_Name)}</b>
                        <br>
                        <small>${esc(item.Item_ID)}</small>
                    </div>
                </div>
            </td>

            <td>${esc(item.Category)}</td>

            <td>
                <b>${esc(item.Available_Quantity)}</b>
                / ${esc(item.Total_Quantity)}
            </td>

            <td>${esc(item.Borrowed_Quantity)}</td>

            <td>${esc(item.Condition)}</td>

            <td>
                <span class="status ${
                    item.Item_Status !== "Available" ? "warn" : ""
                }">
                    ${esc(item.Item_Status)}
                </span>
            </td>
        </tr>
    `).join("");
}


// =========================================================
// BORROWING TABLE
// =========================================================

function renderBorrowings() {
    const table = $("borrowing-table");

    if (!table) return;

    const search = normalize($("borrowing-search")?.value);

    const rows = [...state.transactions]
        .reverse()
        .filter(transaction => {
            return [
                transaction.Transaction_ID,
                transaction.Item_ID,
                transaction.User_ID
            ].join(" ").toLowerCase().includes(search);
        });

    if (!rows.length) {
        table.innerHTML = `
            <tr>
                <td colspan="6" class="empty-state">
                    No borrowing records yet.
                </td>
            </tr>
        `;
        return;
    }

    table.innerHTML = rows.map(transaction => {
        const item = itemById(transaction.Item_ID);

        const dueDate = String(transaction.Due_Date || "");
        const today = new Date().toISOString().slice(0, 10);

        const overdue =
            normalize(transaction.Transaction_Status) === "borrowed" &&
            dueDate &&
            dueDate < today;

        const inspection =
            String(transaction.Transaction_Status || "")
                .includes("Inspection");

        return `
            <tr>
                <td>
                    <b>${esc(transaction.Transaction_ID)}</b>
                </td>

                <td>${esc(transaction.User_ID)}</td>

                <td>
                    ${esc(item?.Item_Name || transaction.Item_ID)}
                </td>

                <td>${esc(transaction.Issue_Date)}</td>

                <td>${esc(transaction.Due_Date)}</td>

                <td>
                    <span class="status ${
                        overdue || inspection ? "warn" : ""
                    }">
                        ${
                            overdue
                                ? "Overdue"
                                : esc(transaction.Transaction_Status)
                        }
                    </span>
                </td>
            </tr>
        `;
    }).join("");
}


// =========================================================
// RESERVATIONS
// =========================================================

function renderReservations() {
    const table = $("reservation-table");

    if (!table) return;

    if (!state.reservations.length) {
        table.innerHTML = `
            <tr>
                <td colspan="6" class="empty-state">
                    No reservation requests yet.
                </td>
            </tr>
        `;
        return;
    }

    table.innerHTML = [...state.reservations]
        .reverse()
        .map(reservation => `
            <tr>
                <td>
                    <b>${esc(reservation.Reservation_ID)}</b>
                </td>

                <td>${esc(reservation.User_ID)}</td>

                <td>${esc(reservation.Item_ID)}</td>

                <td>${esc(reservation.Request_Date)}</td>

                <td>#${esc(reservation.Priority_Number)}</td>

                <td>
                    <span class="status neutral">
                        ${esc(reservation.Reservation_Status)}
                    </span>
                </td>
            </tr>
        `).join("");
}


// =========================================================
// RECENT ACTIVITY
// =========================================================

function renderActivity() {
    const container = $("recent-activity");

    if (!container) return;

    const rows = [...state.transactions].slice(-5).reverse();

    if (!rows.length) {
        container.innerHTML =
            '<div class="empty-state">Activity will appear here after the first checkout.</div>';
        return;
    }

    container.innerHTML = rows.map(transaction => `
        <div class="activity-row">
            <div class="activity-mark">
                ${transaction.Return_Date ? "↩" : "↗"}
            </div>

            <div class="activity-copy">
                <b>${esc(transaction.User_ID)}</b>
                ${transaction.Return_Date ? "returned" : "borrowed"}

                <b>
                    ${esc(
                        itemById(transaction.Item_ID)?.Item_Name ||
                        transaction.Item_ID
                    )}
                </b>

                <small>
                    ${esc(
                        transaction.Return_Date ||
                        transaction.Issue_Date
                    )}
                    ·
                    ${esc(transaction.Transaction_Status)}
                </small>
            </div>
        </div>
    `).join("");
}


// =========================================================
// USERS
// =========================================================

function renderUsers() {
    const table = $("users-table");

    if (!table || !isAdmin()) return;

    if (!state.users.length) {
        table.innerHTML = `
            <tr>
                <td colspan="5">No registered users found.</td>
            </tr>
        `;
        return;
    }

    table.innerHTML = state.users.map(user => `
        <tr>
            <td>${esc(user.Full_Name)}</td>
            <td>${esc(user.USN_or_Staff_ID)}</td>
            <td>${esc(user.Email || "")}</td>
            <td>${esc(user.Role)}</td>
            <td>${esc(user.Account_Status || "Active")}</td>
        </tr>
    `).join("");
}


// =========================================================
// POPULATE BORROW / RESERVATION SELECTS
// =========================================================

function populateSelects() {
    const borrowerSelect = $("borrow-user");

    if (borrowerSelect) {
        borrowerSelect.innerHTML =
            '<option value="">Select borrower</option>';

        state.users
            .filter(user =>
                normalize(user.Account_Status || "Active") === "active"
            )
            .forEach(user => {
                const option = document.createElement("option");

                option.value = user.USN_or_Staff_ID;
                option.textContent =
                    `${user.USN_or_Staff_ID} - ${user.Full_Name || "User"}`;

                borrowerSelect.appendChild(option);
            });
    }

    const reserveUserSelect = $("reserve-user");

    if (reserveUserSelect) {
        reserveUserSelect.innerHTML =
            '<option value="">Select borrower</option>';

        if (isStudent()) {
            const option = document.createElement("option");

            option.value = state.currentUser.user_id;
            option.textContent = state.currentUser.user_id;
            option.selected = true;

            reserveUserSelect.appendChild(option);
            reserveUserSelect.disabled = true;

        } else {
            reserveUserSelect.disabled = false;

            state.users
                .filter(user =>
                    normalize(user.Account_Status || "Active") === "active"
                )
                .forEach(user => {
                    const option = document.createElement("option");

                    option.value = user.USN_or_Staff_ID;
                    option.textContent =
                        `${user.USN_or_Staff_ID} - ${user.Full_Name || "User"}`;

                    reserveUserSelect.appendChild(option);
                });
        }
    }

    const borrowItemSelect = $("borrow-item");

    if (borrowItemSelect) {
        borrowItemSelect.innerHTML =
            '<option value="">Select equipment</option>';

        state.inventory
            .filter(item => Number(item.Available_Quantity || 0) > 0)
            .forEach(item => {
                const option = document.createElement("option");

                option.value = item.Item_ID;
                option.textContent =
                    `${item.Item_Name} - ${item.Item_ID} (${item.Available_Quantity} available)`;

                borrowItemSelect.appendChild(option);
            });
    }

    const reserveItemSelect = $("reserve-item");

    if (reserveItemSelect) {
        reserveItemSelect.innerHTML =
            '<option value="">Select equipment</option>';

        state.inventory.forEach(item => {
            const option = document.createElement("option");

            option.value = item.Item_ID;
            option.textContent = `${item.Item_Name} - ${item.Item_ID}`;

            reserveItemSelect.appendChild(option);
        });
    }

    const returnSelect = $("return-transaction");

    if (returnSelect) {
        returnSelect.innerHTML =
            '<option value="">Select active borrowing</option>';

        state.transactions
            .filter(transaction => {
                const status = normalize(transaction.Transaction_Status);

                return status === "borrowed" || status === "overdue";
            })
            .forEach(transaction => {
                const item = itemById(transaction.Item_ID);

                const option = document.createElement("option");

                option.value = transaction.Transaction_ID;
                option.textContent =
                    `${transaction.Transaction_ID} - ${transaction.User_ID} - ${item?.Item_Name || transaction.Item_ID}`;

                returnSelect.appendChild(option);
            });
    }
}


// =========================================================
// FORM HELPER
// =========================================================

function formObject(form) {
    return Object.fromEntries(new FormData(form).entries());
}


// =========================================================
// BORROW EQUIPMENT - ADMIN AND STAFF
// =========================================================

const borrowForm = $("borrow-form");

if (borrowForm) {
    borrowForm.addEventListener("submit", async event => {
        event.preventDefault();

        if (isStudent()) {
            toast("Students cannot directly borrow equipment.");
            return;
        }

        try {
            const data = formObject(event.target);

            data.user_code = String(data.user_code || "").trim();
            data.item_id = String(data.item_id || "").trim();
            data.purpose = String(data.purpose || "").trim();
            data.due_date = String(data.due_date || "").trim();
            data.quantity = Number(data.quantity || 1);

            if (!data.user_code) {
                toast("Please select a borrower.");
                return;
            }

            if (!data.item_id) {
                toast("Please select equipment.");
                return;
            }

            if (!data.purpose) {
                toast("Please enter the purpose.");
                return;
            }

            if (!data.due_date) {
                toast("Please select the return date.");
                return;
            }

            if (!Number.isInteger(data.quantity) || data.quantity < 1) {
                toast("Quantity must be at least 1.");
                return;
            }

            const selectedItem = itemById(data.item_id);

            if (!selectedItem) {
                toast("Selected equipment was not found.");
                return;
            }

            const available = Number(selectedItem.Available_Quantity || 0);

            if (data.quantity > available) {
                toast(`Only ${available} unit(s) are available.`);
                return;
            }

            const result = await api("/api/borrow", {
                method: "POST",
                body: JSON.stringify(data)
            });

            toast(
                `${result.message} Transaction ID: ${result.transaction_id}`
            );

            event.target.reset();

            if ($("borrow-quantity")) {
                $("borrow-quantity").value = 1;
            }

            closeModal("borrow-modal");
            await loadData();

        } catch (error) {
            console.error("BORROW ERROR:", error);
            toast(error.message);
        }
    });
}


// =========================================================
// RETURN EQUIPMENT - ADMIN AND STAFF
// =========================================================

const returnForm = $("return-form");

if (returnForm) {
    returnForm.addEventListener("submit", async event => {
        event.preventDefault();

        if (isStudent()) {
            toast("Students cannot record equipment returns.");
            return;
        }

        try {
            const data = formObject(event.target);

            data.transaction_id =
                String(data.transaction_id || "").trim();

            data.condition =
                String(data.condition || "").trim();

            if (!data.transaction_id) {
                toast("Please select a borrowing transaction.");
                return;
            }

            if (!data.condition) {
                toast("Please select the return condition.");
                return;
            }

            const result = await api("/api/return", {
                method: "POST",
                body: JSON.stringify(data)
            });

            toast(result.message);

            event.target.reset();
            closeModal("return-modal");

            await loadData();

        } catch (error) {
            console.error("RETURN ERROR:", error);
            toast(error.message);
        }
    });
}


// =========================================================
// RESERVATION - ALL ROLES
// =========================================================

const reserveForm = $("reserve-form");

if (reserveForm) {
    reserveForm.addEventListener("submit", async event => {
        event.preventDefault();

        try {
            const data = formObject(event.target);

            // Students can reserve only for themselves.
            if (isStudent()) {
                data.user_code = state.currentUser.user_id;
            } else {
                data.user_code = String(data.user_code || "").trim();
            }

            data.item_id = String(data.item_id || "").trim();
            data.purpose = String(data.purpose || "").trim();
            data.quantity = Number(data.quantity || 1);

            if (!data.user_code) {
                toast("Please select a borrower.");
                return;
            }

            if (!data.item_id) {
                toast("Please select equipment.");
                return;
            }

            if (!data.purpose) {
                toast("Please enter the purpose.");
                return;
            }

            const result = await api("/api/reservations", {
                method: "POST",
                body: JSON.stringify(data)
            });

            toast(
                `${result.message} ID: ${result.reservation_id}`
            );

            event.target.reset();
            closeModal("reserve-modal");

            await loadData();

        } catch (error) {
            console.error("RESERVATION ERROR:", error);
            toast(error.message);
        }
    });
}


// =========================================================
// MODAL BACKDROP
// =========================================================

document.querySelectorAll(".modal-backdrop").forEach(modal => {
    modal.addEventListener("click", event => {
        if (event.target === modal) {
            modal.classList.remove("show");
        }
    });
});


// =========================================================
// DEFAULT DUE DATE
// =========================================================

function setupDueDate() {
    const dateInput = $("due-date");

    if (!dateInput) return;

    const today = new Date();
    const todayString = today.toISOString().slice(0, 10);

    dateInput.min = todayString;

    const defaultDueDate = new Date();
    defaultDueDate.setDate(defaultDueDate.getDate() + 3);

    dateInput.value = defaultDueDate.toISOString().slice(0, 10);
}

setupDueDate();


// =========================================================
// SEARCH
// =========================================================

const inventorySearch = $("inventory-search");

if (inventorySearch) {
    inventorySearch.addEventListener("input", renderInventory);
}

const borrowingSearch = $("borrowing-search");

if (borrowingSearch) {
    borrowingSearch.addEventListener("input", renderBorrowings);
}


// =========================================================
// LOGIN / DASHBOARD
// =========================================================

const loginScreen = $("login-screen");
const appShell = document.querySelector(".app-shell");

if (appShell) {
    appShell.style.display = "none";
}

function showLogin() {
    if (loginScreen) {
        loginScreen.classList.add("active");
    }

    if (appShell) {
        appShell.style.display = "none";
    }
}

function showDashboard() {
    if (loginScreen) {
        loginScreen.classList.remove("active");
    }

    if (appShell) {
        appShell.style.display = "";
    }
}


// =========================================================
// LOGIN
// =========================================================

const loginForm = $("login-form");

if (loginForm) {
    loginForm.addEventListener("submit", async event => {
        event.preventDefault();

        const errorBox = $("login-error");

        if (errorBox) {
            errorBox.classList.remove("show");
        }

        try {
            const result = await api("/api/login", {
                method: "POST",
                body: JSON.stringify({
                    username: $("login-username")?.value?.trim(),
                    password: $("login-password")?.value
                })
            });

            state.currentUser = {
                user_id: result.user_id || "",
                role: result.role || "",
                username: result.username || ""
            };

            showDashboard();

            const loaded = await loadData();

            if (!loaded) {
                showLogin();
                return;
            }

            switchView("overview");

            toast("Welcome, " + (result.username || "User"));

        } catch (error) {
            if (errorBox) {
                errorBox.textContent = error.message;
                errorBox.classList.add("show");
            } else {
                toast(error.message);
            }
        }
    });
}


// =========================================================
// SESSION CHECK
// =========================================================

async function initializeAuth() {
    try {
        const result = await api("/api/session");

        if (result.logged_in) {
            state.currentUser = {
                user_id: result.user_id || "",
                role: result.role || "",
                username: result.username || ""
            };

            showDashboard();

            const loaded = await loadData();

            if (!loaded) {
                showLogin();
                return;
            }

            switchView("overview");

        } else {
            state.currentUser = {
                user_id: "",
                role: "",
                username: ""
            };

            showLogin();
        }

    } catch (error) {
        console.error("SESSION CHECK ERROR:", error);
        showLogin();
    }
}


// =========================================================
// LOGOUT
// =========================================================

const logoutButton = $("logout-button");

if (logoutButton) {
    logoutButton.addEventListener("click", async () => {
        try {
            await api("/api/logout", {
                method: "POST"
            });

            state = {
                inventory: [],
                transactions: [],
                reservations: [],
                users: [],
                stats: {},
                currentUser: {
                    user_id: "",
                    role: "",
                    username: ""
                }
            };

            showLogin();

            if (loginForm) {
                loginForm.reset();
            }

            toast("Logged out successfully.");

        } catch (error) {
            toast("Logout failed: " + error.message);
        }
    });
}


// =========================================================
// CREATE USER - ADMIN ONLY
// =========================================================

const userForm = $("user-form");

if (userForm) {
    userForm.addEventListener("submit", async event => {
        event.preventDefault();

        if (!isAdmin()) {
            toast("Only Admin can create user accounts.");
            return;
        }

        const formData = new FormData(event.target);

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
            event.target.reset();

            await loadData();

        } catch (error) {
            alert(error.message);
        }
    });
}


// =========================================================
// CHANGE PASSWORD
// =========================================================

const changePasswordScreen = $("change-password-screen");

function showChangePassword() {
    if (loginScreen) {
        loginScreen.classList.remove("active");
    }

    if (changePasswordScreen) {
        changePasswordScreen.classList.add("active");
    }

    if (appShell) {
        appShell.style.display = "none";
    }
}

const changePasswordForm = $("change-password-form");

if (changePasswordForm) {
    changePasswordForm.addEventListener("submit", async event => {
        event.preventDefault();

        const errorBox = $("change-password-error");

        if (errorBox) {
            errorBox.classList.remove("show");
        }

        const currentPassword = $("current-password")?.value;
        const newPassword = $("new-password")?.value;
        const confirmPassword = $("confirm-password")?.value;

        if (newPassword !== confirmPassword) {
            const message = "New passwords do not match.";

            if (errorBox) {
                errorBox.textContent = message;
                errorBox.classList.add("show");
            } else {
                toast(message);
            }

            return;
        }

        try {
            const result = await api("/api/change-password", {
                method: "POST",
                body: JSON.stringify({
                    current_password: currentPassword,
                    new_password: newPassword
                })
            });

            event.target.reset();

            if (changePasswordScreen) {
                changePasswordScreen.classList.remove("active");
            }

            showDashboard();

            const loaded = await loadData();

            if (!loaded) {
                showLogin();
                return;
            }

            toast(result.message);

        } catch (error) {
            if (errorBox) {
                errorBox.textContent = error.message;
                errorBox.classList.add("show");
            } else {
                toast(error.message);
            }
        }
    });
}


// =========================================================
// START APPLICATION
// =========================================================

initializeAuth();
