import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import OfficerConsole from "./officer";
import SimulationDashboard from "./components/SimulationDashboard";
import DistrictDashboard from "./components/DistrictDashboard";
import "./officer.css";

const API = "http://localhost:8000";
const today = new Date().toISOString().slice(0, 10);

async function api(path, options = {}, token) {
  const response = await fetch(`${API}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    ...options,
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(
      typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail)
    );
  }
  return body;
}

function Login({ onToken }) {
  const [register, setRegister] = useState({
    phone: "",
    name: "",
    village: "",
    district: "",
  });
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [message, setMessage] = useState("");

  const registerFarmer = async (e) => {
    e.preventDefault();
    try {
      await api("/farmers", { method: "POST", body: JSON.stringify(register) });
      setPhone(register.phone);
      setMessage("Registered. Request the mock OTP.");
    } catch (x) {
      setMessage(x.message);
    }
  };

  const requestOtp = async () => {
    try {
      const result = await api("/auth/otp/request", {
        method: "POST",
        body: JSON.stringify({ phone }),
      });
      setMessage(`${result.message} Ask the demo operator for the code.`);
    } catch (x) {
      setMessage(x.message);
    }
  };

  const verify = async (e) => {
    e.preventDefault();
    try {
      const result = await api("/auth/otp/verify", {
        method: "POST",
        body: JSON.stringify({ phone, code }),
      });
      onToken(result.token);
      setMessage("Signed in.");
    } catch (x) {
      setMessage(x.message);
    }
  };

  return (
    <section className="farmer-screen">
      <h1>Register or login</h1>
      <form onSubmit={registerFarmer}>
        <h2>Register</h2>
        {Object.keys(register).map((key) => (
          <label key={key}>
            {key}
            <input
              required
              value={register[key]}
              onChange={(e) => setRegister({ ...register, [key]: e.target.value })}
            />
          </label>
        ))}
        <button>Register</button>
      </form>
      <form onSubmit={verify}>
        <h2>Mock OTP login</h2>
        <label>
          Phone
          <input
            required
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
        </label>
        <button type="button" onClick={requestOtp}>
          Request OTP
        </button>
        <label>
          OTP
          <input
            required
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
        </label>
        <button>Verify</button>
      </form>
      {message && <p className="message">{message}</p>}
    </section>
  );
}

function Booking({ token }) {
  const [form, setForm] = useState({
    crop: "Wheat",
    declared_qtl: "20",
    district: "Sehore",
    lat: "23.2033",
    lng: "77.0844",
    date: today,
  });
  const [centres, setCentres] = useState([]);
  const [message, setMessage] = useState("");
  const [alternatives, setAlternatives] = useState([]);

  const search = async (e) => {
    e.preventDefault();
    try {
      setCentres(
        await api(
          `/centres/nearby?${new URLSearchParams({
            lat: form.lat,
            lng: form.lng,
            date: form.date,
            qtl: form.declared_qtl,
            district: form.district,
          })}`
        )
      );
    } catch (x) {
      setMessage(x.message);
    }
  };

  const book = async (centre) => {
    if (!token) return setMessage("Sign in before booking.");
    try {
      const result = await api(
        "/bookings",
        {
          method: "POST",
          body: JSON.stringify({
            centre_id: centre.centre_id,
            date: form.date,
            crop: form.crop,
            declared_qtl: Number(form.declared_qtl),
          }),
        },
        token
      );
      setMessage(
        `Slot confirmed: ${result.date} at ${result.hour}:00. Lot ${result.lot_id}.`
      );
    } catch (x) {
      try {
        const detail = JSON.parse(x.message);
        setMessage(detail.reason);
        setAlternatives(detail.alternatives || []);
      } catch {
        setMessage(x.message);
      }
    }
  };

  return (
    <section className="farmer-screen">
      <h1>Book a slot</h1>
      <form onSubmit={search}>
        <label>
          Crop
          <select
            value={form.crop}
            onChange={(e) => setForm({ ...form, crop: e.target.value })}
          >
            <option>Wheat</option>
            <option>Paddy</option>
          </select>
        </label>
        <label>
          Declared quintals
          <input
            type="number"
            min="0.01"
            required
            value={form.declared_qtl}
            onChange={(e) => setForm({ ...form, declared_qtl: e.target.value })}
          />
        </label>
        <label>
          District
          <input
            required
            value={form.district}
            onChange={(e) => setForm({ ...form, district: e.target.value })}
          />
        </label>
        <label>
          Date
          <input
            type="date"
            required
            value={form.date}
            onChange={(e) => setForm({ ...form, date: e.target.value })}
          />
        </label>
        <button>Find centres</button>
      </form>
      {message && <p className="message">{message}</p>}
      <div className="centre-list">
        {centres.map((centre) => (
          <article
            className={`centre-card ${centre.status === "Choked" ? "choked" : ""}`}
            key={centre.centre_id}
          >
            <h2>{centre.name}</h2>
            <p>
              {centre.next_available_date} · {centre.distance_km ?? "—"} km
            </p>
            <strong>{centre.status}</strong>
            {centre.reason && <p>{centre.reason}</p>}
            {centre.status !== "Choked" && (
              <button onClick={() => book(centre)}>Book this centre</button>
            )}
          </article>
        ))}
      </div>
      {alternatives.length > 0 && (
        <aside>
          <h2>Nearest open alternatives</h2>
          {alternatives.map((centre) => (
            <p key={centre.centre_id}>
              {centre.name}: {centre.distance_km ?? "—"} km, {centre.next_available_date}
            </p>
          ))}
        </aside>
      )}
    </section>
  );
}

function Lots({ token }) {
  const [lots, setLots] = useState([]);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (token)
      api("/bookings/mine", {}, token)
        .then(async (rows) =>
          setLots(
            await Promise.all(
              rows.map((row) => api(`/lots/${row.lot_id}/status`, {}, token))
            )
          )
        )
        .catch((x) => setMessage(x.message));
  }, [token]);

  if (!token)
    return (
      <section className="farmer-screen">
        <h1>My lots</h1>
        <p>Sign in to view your lots.</p>
      </section>
    );

  return (
    <section className="farmer-screen">
      <h1>My lots</h1>
      {message && <p className="message">{message}</p>}
      {lots.map((lot) => (
        <article className="lot" key={lot.lot_id}>
          <h2>
            Lot {lot.lot_id}: {lot.state}
          </h2>
          {lot.state === "ARRIVED" && (
            <p className="queue-position">
              Live queue position: {lot.queue_position}
            </p>
          )}
          <ol className="timeline">
            {[
              "REGISTERED",
              "ARRIVED",
              "WEIGHED",
              "GRADED",
              "LIFTED",
              "SETTLED",
            ].map((state) => {
              const event = lot.events.find((row) => row.to_state === state);
              return (
                <li className={event ? "complete" : ""} key={state}>
                  <strong>{state}</strong>
                  <span>
                    {event?.created_at
                      ? new Date(event.created_at).toLocaleString()
                      : "Pending"}
                  </span>
                </li>
              );
            })}
          </ol>
        </article>
      ))}
    </section>
  );
}

function Queue() {
  const [centre, setCentre] = useState("1");
  const [queue, setQueue] = useState([]);
  return (
    <section className="farmer-screen">
      <h1>Live queue board</h1>
      <label>
        Centre ID
        <input value={centre} onChange={(e) => setCentre(e.target.value)} />
      </label>
      <button
        onClick={() =>
          api(`/centres/${centre}/queue`).then((result) => setQueue(result.queue))
        }
      >
        Refresh
      </button>
      <ol>
        {queue.map((row) => (
          <li key={row.lot_id}>
            Token {row.token_no} — position {row.position}
          </li>
        ))}
      </ol>
    </section>
  );
}

function SmsPanel() {
  const [messages, setMessages] = useState([]);
  useEffect(() => {
    const load = () =>
      api("/dev/notifications")
        .then(setMessages)
        .catch(() => {});
    load();
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, []);
  return (
    <aside className="phone-panel">
      <header>Mock SMS inbox</header>
      <div>
        {messages.map((message) => (
          <p
            className={message.status === "SENT" ? "sms sent" : "sms"}
            key={message.id}
          >
            {message.body}
            <small>{message.status}</small>
          </p>
        ))}
      </div>
    </aside>
  );
}

function App() {
  const [screen, setScreen] = useState("login");
  const [token, setToken] = useState("");
  return (
    <main className="farmer-app">
      <nav>
        <button onClick={() => setScreen("login")}>Register/Login</button>
        <button onClick={() => setScreen("booking")}>Book a slot</button>
        <button onClick={() => setScreen("lots")}>My Lots</button>
        <button onClick={() => setScreen("queue")}>Live queue</button>
        <button onClick={() => setScreen("officer")}>Officer console</button>
        <button onClick={() => setScreen("district")}>District console</button>
        <button onClick={() => setScreen("sim")}>Simulation</button>
      </nav>
      <div className="app-layout">
        <div>
          {screen === "login" && <Login onToken={setToken} />}
          {screen === "booking" && <Booking token={token} />}
          {screen === "lots" && <Lots token={token} />}
          {screen === "queue" && <Queue />}
          {screen === "officer" && <OfficerConsole />}
          {screen === "district" && <DistrictDashboard />}
          {screen === "sim" && <SimulationDashboard />}
        </div>
        <SmsPanel />
      </div>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
