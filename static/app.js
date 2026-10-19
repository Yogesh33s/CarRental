const $ = (id) => document.getElementById(id);



let allCars = [];

let allCustomers = [];

let allRentals = [];

let revenueChart = null;

let categoryChart = null;

let modalType = "";

let maintenanceCarId = null;



const pageInfo = {

  dashboard: ["Dashboard", "Overview of your rental operations and earnings"],

  cars: ["Cars", "Manage your fleet, availability and hourly rates"],

  customers: ["Customers", "Registered customers and driver license information"],

  rent: ["Rent a Car", "Book a vehicle by the hour"],

  history: ["Rental History", "Active and completed rental bookings"]

};



function money(value) {

  return "₹" + Number(value || 0).toLocaleString("en-IN", {

    minimumFractionDigits: 2,

    maximumFractionDigits: 2

  });

}



function hourlyRate(car) {

  return Number(car?.hourly_rate ?? car?.daily_rate ?? 0);

}



function toast(message, isError = false) {

  const el = $("toast");

  if (!el) {

    alert(message);

    return;

  }

  el.textContent = message;

  el.style.background = isError ? "#b42332" : "#17233b";

  el.classList.add("show");

  clearTimeout(toast.timer);

  toast.timer = setTimeout(() => el.classList.remove("show"), 3500);

}



async function api(url, options = {}) {

  const response = await fetch(url, {

    ...options,

    headers: {

      ...(options.body ? { "Content-Type": "application/json" } : {}),

      ...options.headers

    }

  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) throw new Error(data.error || "Request failed");

  return data;

}



function makeCell(value, className = "") {

  const td = document.createElement("td");

  td.textContent = value ?? "—";

  if (className) td.className = className;

  return td;

}



function makeButton(label, className, handler) {

  const button = document.createElement("button");

  button.type = "button";

  button.textContent = label;

  button.className = `btn ${className}`;

  button.addEventListener("click", handler);

  return button;

}



function badge(status) {

  const span = document.createElement("span");

  span.className = "badge badge-" + String(status || "").toLowerCase();

  span.textContent = status || "Unknown";

  return span;

}



function todayISO(offsetDays = 0) {

  const d = new Date();

  d.setDate(d.getDate() + offsetDays);

  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);

  return local.toISOString().slice(0, 10);

}



function showPage(name) {

  if (!pageInfo[name]) return;

  document.querySelectorAll(".page").forEach((el) => {

    el.classList.toggle("active", el.id === `page-${name}`);

  });

  document.querySelectorAll(".nav button[data-page]").forEach((el) => {

    el.classList.toggle("active", el.dataset.page === name);

  });

  if ($("pageTitle")) $("pageTitle").textContent = pageInfo[name][0];

  if ($("pageSubtitle")) $("pageSubtitle").textContent = pageInfo[name][1];

  if (name === "rent") {

    populateAvailableCars();

    populateCustomerPicker();

  }

}



document.querySelectorAll(".nav button[data-page]").forEach((button) => {

  button.addEventListener("click", () => showPage(button.dataset.page));

});

document.querySelectorAll("[data-go]").forEach((button) => {

  button.addEventListener("click", () => showPage(button.dataset.go));

});



// ---------------- DASHBOARD ----------------



async function loadDashboard() {

  const data = await api("/api/dashboard");

  $("totalCars").textContent = data.total_cars ?? 0;

  $("availableCars").textContent = data.available_cars ?? 0;

  $("rentedCars").textContent = data.rented_cars ?? 0;

  $("customerCount").textContent = data.customers ?? 0;

  $("revenue").textContent = money(data.total_revenue);



  const monthly = (data.months || []).map((month, i) => ({

    month,

    revenue: Number((data.monthly_revenue || [])[i] || 0)

  }));



  if (revenueChart) revenueChart.destroy();

  revenueChart = new Chart($("revenueChart"), {

    type: "line",

    data: {

      labels: monthly.map((x) => x.month),

      datasets: [{

        label: "Revenue",

        data: monthly.map((x) => x.revenue),

        borderColor: "#2864ed",

        backgroundColor: "rgba(40,100,237,.12)",

        pointRadius: 4,

        tension: 0.3,

        fill: true

      }]

    },

    options: {

      responsive: true,

      maintainAspectRatio: false,

      plugins: { legend: { display: false } }

    }

  });



  if (categoryChart) categoryChart.destroy();

  const categoryData = data.categories || [];

  categoryChart = new Chart($("categoryChart"), {

    type: "doughnut",

    data: {

      labels: categoryData.map((x) => x._id || "Other"),

      datasets: [{

        data: categoryData.map((x) => x.count || 0),

        backgroundColor: ["#2864ed", "#10b981", "#f59e0b", "#a855f7", "#f43f5e", "#06b6d4"],

        borderWidth: 2,

        borderColor: "#ffffff"

      }]

    },

    options: {

      responsive: true,

      maintainAspectRatio: false,

      plugins: { legend: { position: "right" } }

    }

  });

}



// ---------------- CARS ----------------



async function loadCars() {

  allCars = await api("/api/cars");

  const search = $("carSearch").value.trim().toLowerCase();

  const category = $("carCategoryFilter").value;

  const status = $("carStatusFilter").value;



  const filtered = allCars.filter((car) => {

    const text = `${car.make} ${car.model} ${car.license_plate} ${car.vin}`.toLowerCase();

    return text.includes(search) &&

      (!category || car.category === category) &&

      (!status || car.status === status);

  });



  const body = $("carsBody");

  body.replaceChildren();



  if (!filtered.length) {

    const row = document.createElement("tr");

    const td = makeCell("No cars found. Add your first vehicle to get started.");

    td.colSpan = 7;

    td.className = "empty";

    row.appendChild(td);

    body.appendChild(row);

  }



  filtered.forEach((car) => {

    const row = document.createElement("tr");

    const details = document.createElement("td");

    const name = document.createElement("div");

    name.className = "primary-text";

    name.textContent = `${car.year} ${car.make} ${car.model}`;

    const specs = document.createElement("div");

    specs.className = "secondary-text";

    specs.textContent = `${car.fuel_type || ""} • ${car.transmission || ""}`;

    details.append(name, specs);

    row.appendChild(details);

    row.appendChild(makeCell(car._id));

    row.appendChild(makeCell(car.category));

    row.appendChild(makeCell(`${money(hourlyRate(car))}/hr`));

    row.appendChild(makeCell(car.license_plate));



    const statusCell = document.createElement("td");

    statusCell.appendChild(badge(car.status));

    row.appendChild(statusCell);



    const actions = document.createElement("td");



    if (car.status === "Maintenance") {

      actions.appendChild(makeButton("✓ Maintenance Done", "btn-success", async () => {

        if (!confirm(`Mark ${car.make} ${car.model} as available for rental?`)) return;

        try {

          await api(`/api/cars/${car._id}/maintenance-complete`, { method: "POST" });

          toast("Maintenance completed. Vehicle is available.");

          await refresh();

        } catch (e) {

          toast(e.message, true);

        }

      }));

    } else if (car.status !== "Rented") {

      actions.appendChild(makeButton("🗑 Remove", "btn-light", async () => {

        if (!confirm("Remove this vehicle?")) return;

        try {

          await api(`/api/cars/${car._id}`, { method: "DELETE" });

          toast("Vehicle removed.");

          await refresh();

        } catch (e) {

          toast(e.message, true);

        }

      }));

    } else {

      actions.textContent = "Active rental";

    }



    row.appendChild(actions);

    body.appendChild(row);

  });



  populateAvailableCars();

}



function populateAvailableCars() {

  const select = $("rentCarSelect");

  if (!select) return;

  const previous = select.value;

  select.replaceChildren();



  const placeholder = document.createElement("option");

  placeholder.value = "";

  placeholder.textContent = "-- Choose an available car --";

  select.appendChild(placeholder);



  allCars.filter((car) => car.status === "Available").forEach((car) => {

    const option = document.createElement("option");

    option.value = car.license_plate;

    option.textContent = `${car.make} ${car.model} • ${car.license_plate} • ${money(hourlyRate(car))}/hr`;

    select.appendChild(option);

  });



  if ([...select.options].some((option) => option.value === previous)) {

    select.value = previous;

  }

  updateRentalPreview();

}



// ---------------- CUSTOMERS ----------------



async function loadCustomers() {

  allCustomers = await api("/api/customers");

  const search = $("customerSearch").value.trim().toLowerCase();

  const filtered = allCustomers.filter((customer) =>

    `${customer.name} ${customer.email} ${customer.phone}`.toLowerCase().includes(search)

  );



  const body = $("customersBody");

  body.replaceChildren();



  if (!filtered.length) {

    const row = document.createElement("tr");

    const td = makeCell("No customers found.");

    td.colSpan = 7;

    td.className = "empty";

    row.appendChild(td);

    body.appendChild(row);

  }



  filtered.forEach((customer) => {

    const row = document.createElement("tr");

    row.appendChild(makeCell(`#${customer.customer_id ?? "—"} · ${customer.name}`, "primary-text"));

    row.appendChild(makeCell(customer.email));

    row.appendChild(makeCell(customer.phone));

    row.appendChild(makeCell(customer.license_number));

    row.appendChild(makeCell(customer.city));

    row.appendChild(makeCell(money(customer.total_spending)));



    const action = document.createElement("td");

    action.appendChild(makeButton("🗑 Remove", "btn-light", async () => {

      if (!confirm("Remove this customer?")) return;

      try {

        await api(`/api/customers/${customer._id}`, { method: "DELETE" });

        toast("Customer removed.");

        await refresh();

      } catch (e) {

        toast(e.message, true);

      }

    }));

    row.appendChild(action);

    body.appendChild(row);

  });



  populateCustomerPicker();

}



function setupCustomerPicker() {
  const idSelect = $("rentalCustomerId");
  const emailSelect = $("rentEmail");
  if (!idSelect || !emailSelect) return;

  if (!idSelect.dataset.pickerBound) {
    idSelect.dataset.pickerBound = "true";
    idSelect.addEventListener("change", () => {
      const customer = allCustomers.find(c => String(c.customer_id) === idSelect.value);
      selectRentalCustomer(customer, "id");
    });
  }

  if (!emailSelect.dataset.pickerBound) {
    emailSelect.dataset.pickerBound = "true";
    emailSelect.addEventListener("change", () => {
      const customer = allCustomers.find(c => c.email === emailSelect.value);
      selectRentalCustomer(customer, "email");
    });
  }
}

function populateCustomerPicker() {
  const idSelect = $("rentalCustomerId");
  const emailSelect = $("rentEmail");
  if (!idSelect || !emailSelect) return;

  const previousId = idSelect.value;
  const previousEmail = emailSelect.value;
  idSelect.replaceChildren();
  emailSelect.replaceChildren();

  idSelect.add(new Option("-- Select Customer ID --", ""));
  emailSelect.add(new Option("-- Select Email Address --", ""));

  allCustomers.forEach(customer => {
    idSelect.add(new Option(String(customer.customer_id ?? "—"), String(customer.customer_id ?? "")));
    emailSelect.add(new Option(customer.email || "", customer.email || ""));
  });

  const selected = allCustomers.find(c =>
    String(c.customer_id) === previousId || c.email === previousEmail
  );
  if (selected) {
    idSelect.value = String(selected.customer_id ?? "");
    emailSelect.value = selected.email || "";
    applySelectedCustomer(selected);
  } else {
    idSelect.value = "";
    emailSelect.value = "";
    applySelectedCustomer(null);
  }
}

function selectRentalCustomer(customer, source) {
  const idSelect = $("rentalCustomerId");
  const emailSelect = $("rentEmail");
  if (!customer) {
    if (idSelect) idSelect.value = "";
    if (emailSelect) emailSelect.value = "";
    applySelectedCustomer(null);
    return;
  }

  if (source === "id") emailSelect.value = customer.email || "";
  else idSelect.value = String(customer.customer_id ?? "");

  applySelectedCustomer(customer);
}

function applySelectedCustomer(customer) {
  $("rentName").value = customer?.name || "";
  $("rentPhone").value = customer?.phone || "";
  $("rentLicense").value = customer?.license_number || "";
  $("rentCity").value = customer?.city || "";
  updateRentalPreview();
}


// ---------------- RENTAL HISTORY ----------------



async function loadRentals() {

  allRentals = await api("/api/rentals");

  const search = $("rentalSearch").value.trim().toLowerCase();

  const status = $("rentalStatusFilter").value;



  const filtered = allRentals.filter((rental) =>

    `${rental.booking_code} ${rental.customer_name} ${rental.car_name}`.toLowerCase().includes(search) &&

    (!status || rental.status === status)

  );



  const body = $("rentalsBody");

  body.replaceChildren();



  if (!filtered.length) {

    const row = document.createElement("tr");

    const td = makeCell("No rental records found. New bookings will appear here.");

    td.colSpan = 8;

    td.className = "empty";

    row.appendChild(td);

    body.appendChild(row);

  }



  filtered.forEach((rental) => {

    const row = document.createElement("tr");

    row.appendChild(makeCell(rental.booking_code, "primary-text"));



    const customerCell = document.createElement("td");

    const customerName = document.createElement("div");

    customerName.className = "primary-text";

    const visibleCustomerId = rental.customer_numeric_id ? `#${rental.customer_numeric_id} · ` : "";

    customerName.textContent = `${visibleCustomerId}${rental.customer_name || "—"}`;

    const customerEmail = document.createElement("div");

    customerEmail.className = "secondary-text";

    customerEmail.textContent = rental.customer_email || "";

    customerCell.append(customerName, customerEmail);

    row.appendChild(customerCell);



    row.appendChild(makeCell(`${rental.car_name || ""} (${rental.license_plate || ""})`));

    const startDisplay = `${rental.start_date || ""} ${rental.start_time || ""}`.trim();

    const endDisplay = `${rental.end_date || ""} ${rental.end_time || ""}`.trim();

    row.appendChild(makeCell(`${startDisplay} → ${endDisplay}`));



    const duration = Number(rental.duration_hours || 0);

    row.appendChild(makeCell(`${duration} hour${duration === 1 ? "" : "s"}`));



    const discount = Number(rental.discount_amount || 0);

    const finalAmount = rental.final_amount ?? rental.total_amount ?? 0;

    row.appendChild(makeCell(money(finalAmount)));



    const statusCell = document.createElement("td");

    statusCell.appendChild(badge(rental.status));

    row.appendChild(statusCell);



    const action = document.createElement("td");

    if (rental.status === "Rented") {

      action.appendChild(makeButton("✓ Return Car", "btn-success", () => openReturnForm(rental)));

    } else {

      action.textContent = "Returned";

    }

    row.appendChild(action);

    body.appendChild(row);

  });

}



// ---------------- HOURLY RENTAL PREVIEW ----------------



function updateRentalPreview() {

  const name = $("rentName")?.value.trim() || "";

  const selectedCustomerId = $("rentalCustomerId")?.value || "";

  const selectedEmail = $("rentEmail")?.value || "";

  const selectedCustomer = allCustomers.find((c) =>
    String(c.customer_id) === selectedCustomerId || c.email === selectedEmail
  );

  const email = selectedCustomer?.email || "";

  const plate = $("rentCarSelect")?.value || "";

  const car = allCars.find((c) => c.license_plate === plate);



  if ($("rentPlate")) $("rentPlate").value = plate;

  if ($("dailyRate")) {

    $("dailyRate").value = car ? `${money(hourlyRate(car))}/hr` : "Select a car first";

  }



  const start = $("startDate").value;

  const startTime = $("startTime").value;

  const end = $("endDate").value;

  const endTime = $("endTime").value;



  let hours = 0;

  let total = 0;

  let validPeriod = false;



  if (start && startTime && end && endTime) {

    const startDateTime = new Date(`${start}T${startTime}`);

    const endDateTime = new Date(`${end}T${endTime}`);

    const difference = endDateTime - startDateTime;

    if (Number.isFinite(difference) && difference > 0) {

      hours = Math.ceil(difference / 3600000);

      total = car ? hours * hourlyRate(car) : 0;

      validPeriod = true;

    }

  }



  if ($("duration")) {

    $("duration").value = validPeriod

      ? `${hours} hour${hours === 1 ? "" : "s"}`

      : "Choose valid dates and times";

  }

  if ($("summaryCustomer")) $("summaryCustomer").textContent = name || "Select a registered customer";

  if ($("summaryEmail")) $("summaryEmail").textContent = email || "Customer email will appear here";

  if ($("summaryCar")) $("summaryCar").textContent = car ? `${car.make} ${car.model}` : "No Car Selected";

  if ($("summaryRate")) $("summaryRate").textContent = `Rate: ${money(car ? hourlyRate(car) : 0)} / hr`;

  if ($("summaryDates")) {

    $("summaryDates").textContent = validPeriod

      ? `${start} ${startTime} → ${end} ${endTime}`

      : "Choose rental dates and times";

  }

  if ($("summaryDuration")) {

    $("summaryDuration").textContent = `Duration: ${validPeriod ? `${hours} hour${hours === 1 ? "" : "s"}` : "—"}`;

  }

  if ($("summaryBase")) $("summaryBase").textContent = money(total);

  if ($("summaryTotal")) $("summaryTotal").textContent = money(total);

}



["startDate", "startTime", "endDate", "endTime", "rentCarSelect"].forEach((id) => {

  $(id)?.addEventListener("input", updateRentalPreview);

  $(id)?.addEventListener("change", updateRentalPreview);

});



$("rentalForm")?.addEventListener("reset", () => {

  setTimeout(() => {

    $("startDate").value = todayISO();

    $("startTime").value = "09:00";

    $("endDate").value = todayISO();

    $("endTime").value = "10:00";

    if ($("rentName")) $("rentName").value = "";

    if ($("rentalCustomerId")) $("rentalCustomerId").value = "";

    if ($("rentEmail")) $("rentEmail").value = "";

    applySelectedCustomer(null);
    updateRentalPreview();

  }, 0);

});



$("rentalForm")?.addEventListener("submit", async (event) => {

  event.preventDefault();

  const form = event.currentTarget;

  const selectedCustomerId = $("rentalCustomerId")?.value || "";

  const selectedEmail = $("rentEmail")?.value || "";

  const selectedCustomer = allCustomers.find((c) =>
    String(c.customer_id) === selectedCustomerId || c.email === selectedEmail
  );

  const data = {

    customer_id: selectedCustomer?.customer_id || "",

    customer_email: selectedCustomer?.email || "",

    license_plate: $("rentCarSelect").value,

    start_date: $("startDate").value,

    start_time: $("startTime").value,

    end_date: $("endDate").value,

    end_time: $("endTime").value

  };



  if (!selectedCustomer) {

    toast("Select a registered customer ID first.", true);

    return;

  }

  if (!data.license_plate) {

    toast("Please select an available car.", true);

    return;

  }

  if (!data.start_date || !data.start_time || !data.end_date || !data.end_time) {

    toast("Please select both dates and times.", true);

    return;

  }



  const start = new Date(`${data.start_date}T${data.start_time}`);

  const end = new Date(`${data.end_date}T${data.end_time}`);

  if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) || end <= start) {

    toast("End date and time must be after the start.", true);

    return;

  }



  try {

    const result = await api("/api/rentals", {

      method: "POST",

      body: JSON.stringify(data)

    });

    toast(`Booking ${result.booking_code} created successfully!`);

    form.reset();

    await refresh();

    showPage("history");

  } catch (e) {

    toast(e.message, true);

  }

});



// ---------------- ADD CAR / CUSTOMER MODALS ----------------



const backdrop = $("modalBackdrop");



function closeModal() {

  backdrop.classList.remove("open");

}



$("closeModal").addEventListener("click", closeModal);

$("cancelModal").addEventListener("click", closeModal);

backdrop.addEventListener("click", (event) => {

  if (event.target === backdrop) closeModal();

});



function addField(container, label, name, placeholder, type = "text", required = true) {

  const wrapper = document.createElement("div");

  wrapper.className = "field";

  const title = document.createElement("label");

  title.textContent = label;

  let input;



  if (type.startsWith("select-")) {

    input = document.createElement("select");

    let options = [];

    if (type === "select-category") options = ["Sedan", "SUV", "Hatchback", "Convertible", "Truck", "Minivan"];

    else if (type === "select-fuel") options = ["Petrol", "Diesel", "Electric", "Hybrid"];

    else if (type === "select-transmission") options = ["Manual", "Automatic"];

    else if (type === "select-condition") options = ["Good", "Scratched", "Damaged"];

    else if (type === "select-maintenance") options = ["No", "Yes"];



    input.add(new Option("Choose " + label.toLowerCase(), ""));

    options.forEach((option) => input.add(new Option(option, option)));

  } else {

    input = document.createElement("input");

    input.type = type;

    input.placeholder = placeholder;

  }



  input.name = name;

  input.required = required;

  if (type === "number") {

    input.min = "0";

    input.step = "0.01";

  }

  wrapper.append(title, input);

  container.appendChild(wrapper);

}



function openRecordModal(type) {

  modalType = type;

  $("modalTitle").textContent = type === "car" ? "🚗 Add New Car" : "👥 Add New Customer";

  const fields = $("modalFields");

  fields.replaceChildren();



  if (type === "car") {

    addField(fields, "Make *", "make", "e.g. Hyundai");

    addField(fields, "Model *", "model", "e.g. Creta");

    addField(fields, "Year *", "year", "Enter model year", "number");

    addField(fields, "Category *", "category", "", "select-category");

    addField(fields, "Hourly Rate (₹) *", "hourly_rate", "Enter hourly rate", "number");

    addField(fields, "License Plate *", "license_plate", "Enter license plate");

    addField(fields, "VIN *", "vin", "Enter vehicle VIN");

    addField(fields, "Fuel Type *", "fuel_type", "", "select-fuel");

    addField(fields, "Transmission *", "transmission", "", "select-transmission");

  } else {

    addField(fields, "Full Name *", "name", "Enter customer name");

    addField(fields, "Email *", "email", "Enter email address", "email");

    addField(fields, "Phone *", "phone", "Enter phone number");

    addField(fields, "Driver License *", "license_number", "Enter license number");

    addField(fields, "City *", "city", "Enter city");

  }



  $("modalForm").onsubmit = null;

  backdrop.classList.add("open");

}



$("addCarBtn").addEventListener("click", () => openRecordModal("car"));

$("addCustomerBtn").addEventListener("click", () => openRecordModal("customer"));



$("modalForm").addEventListener("submit", async (event) => {

  event.preventDefault();

  const form = event.currentTarget;

  const data = Object.fromEntries(new FormData(form));

  if (modalType === "return" || modalType === "maintenance") return;



  if (modalType === "car") {

    data.year = Number(data.year);

    data.hourly_rate = Number(data.hourly_rate);

  }



  try {

    await api(modalType === "car" ? "/api/cars" : "/api/customers", {

      method: "POST",

      body: JSON.stringify(data)

    });

    closeModal();

    form.reset();

    toast(modalType === "car" ? "Car added successfully!" : "Customer registered!");

    await refresh();

  } catch (e) {

    toast(e.message, true);

  }

});



// ---------------- RETURN VEHICLE + DISCOUNT ----------------



function openReturnForm(rental) {

  modalType = "return";

  $("modalTitle").textContent = "✓ Return Vehicle";

  const fields = $("modalFields");

  fields.replaceChildren();



  const heading = document.createElement("p");

  heading.textContent = `${rental.car_name} • Booking ${rental.booking_code}`;

  heading.style.gridColumn = "1 / -1";

  fields.appendChild(heading);



  addField(fields, "Actual Return Date *", "returned_date", "", "date");

  addField(fields, "Vehicle Condition *", "condition", "", "select-condition");

  addField(fields, "Late Fee (₹)", "late_fee", "Enter late fee", "number");

  addField(fields, "Damage Charge (₹)", "damage_charge", "Enter damage charge", "number");

  addField(fields, "Discount (₹)", "discount_amount", "Enter fixed discount in rupees", "number");

  addField(fields, "Maintenance Required?", "maintenance", "", "select-maintenance");

  addField(fields, "Return Notes", "return_notes", "Describe scratches or damage", "text", false);



  fields.querySelector('[name="returned_date"]').value = todayISO();

  fields.querySelector('[name="condition"]').value = "Good";

  fields.querySelector('[name="maintenance"]').value = "No";

  fields.querySelector('[name="late_fee"]').value = "0";

  fields.querySelector('[name="damage_charge"]').value = "0";

  fields.querySelector('[name="discount_amount"]').value = "0";



  const updateBillPreview = () => {

    const base = Number(rental.total_amount || 0);

    const late = Number(fields.querySelector('[name="late_fee"]').value || 0);

    const damage = Number(fields.querySelector('[name="damage_charge"]').value || 0);

    const discount = Number(fields.querySelector('[name="discount_amount"]').value || 0);

    let preview = fields.querySelector("#returnBillPreview");

    if (!preview) {

      preview = document.createElement("p");

      preview.id = "returnBillPreview";

      preview.style.gridColumn = "1 / -1";

      preview.style.fontWeight = "700";

      fields.appendChild(preview);

    }

    const total = base + late + damage - discount;

    preview.textContent = `Rental: ${money(base)}  + Late fee: ${money(late)} + Damage: ${money(damage)} − Discount: ${money(discount)} = ${money(total)}`;

    preview.style.color = discount > base + late + damage || [late, damage, discount].some((v) => !Number.isFinite(v) || v < 0)

      ? "#b42332" : "inherit";

  };



  ["late_fee", "damage_charge", "discount_amount"].forEach((name) => {

    fields.querySelector(`[name="${name}"]`).addEventListener("input", updateBillPreview);

  });

  updateBillPreview();



  $("modalForm").onsubmit = async (event) => {

    event.preventDefault();

    const formData = Object.fromEntries(new FormData(event.currentTarget));



    for (const key of ["late_fee", "damage_charge", "discount_amount"]) {

      formData[key] = Number(formData[key] || 0);

      if (!Number.isFinite(formData[key]) || formData[key] < 0) {

        toast("Fees and discount must be valid non-negative amounts.", true);

        return;

      }

    }



    const base = Number(rental.total_amount || 0);

    if (formData.discount_amount > base + formData.late_fee + formData.damage_charge) {

      toast("Discount cannot exceed the total bill.", true);

      return;

    }



    formData.maintenance = formData.maintenance === "Yes";

    try {

      await api(`/api/rentals/${rental._id}/return`, {

        method: "POST",

        body: JSON.stringify(formData)

      });

      closeModal();

      toast("Return recorded.");

      await refresh();

    } catch (e) {

      toast(e.message, true);

    }

  };



  backdrop.classList.add("open");

}



// ---------------- FILTERS & REFRESH ----------------



$("carSearch").addEventListener("input", loadCars);

$("carCategoryFilter").addEventListener("change", loadCars);

$("carStatusFilter").addEventListener("change", loadCars);

$("customerSearch").addEventListener("input", loadCustomers);

$("rentalSearch").addEventListener("input", loadRentals);

$("rentalStatusFilter").addEventListener("change", loadRentals);



async function refresh() {

  try {

    await Promise.all([

      loadCars(),

      loadCustomers(),

      loadRentals(),

      loadDashboard()

    ]);

    setupCustomerPicker();

    populateCustomerPicker();

  } catch (e) {

    console.error(e);

    toast("Could not load data: " + e.message, true);

  }

}



// ---------------- INITIALIZE ----------------



$("startDate").value = todayISO();

$("startTime").value = "09:00";

$("endDate").value = todayISO();

$("endTime").value = "10:00";



setupCustomerPicker();

refresh();

updateRentalPreview();
