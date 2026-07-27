import React, { useState } from "react";

/*
 * IMPORTANT: this calls a RELATIVE path "/api/entries", never a hardcoded
 * backend hostname/IP. Why: the browser (running this JS) talks to the
 * public ALB over your domain. The ALB has a listener rule that forwards
 * anything under /api/* to the backend target group (see doc 05). This
 * means the frontend never needs to know the backend's private IP -- and
 * indeed it COULDN'T, since the backend has no public address at all.
 */
const API_BASE = "/api";

function App() {
  const [text, setText] = useState("");
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [hasListed, setHasListed] = useState(false);

  async function handleInsert() {
    if (!text.trim()) {
      setError("Please enter some text before inserting.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/entries`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Request failed with status ${res.status}`);
      }
      setText("");
      // If the list is already showing, refresh it so the new entry appears immediately.
      if (hasListed) {
        await handleList();
      }
    } catch (err) {
      setError(err.message || "Failed to insert entry.");
    } finally {
      setLoading(false);
    }
  }

  async function handleList() {
    setError("");
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/entries`);
      if (!res.ok) {
        throw new Error(`Request failed with status ${res.status}`);
      }
      const data = await res.json();
      setEntries(data);
      setHasListed(true);
    } catch (err) {
      setError(err.message || "Failed to load entries.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={styles.container}>
      <h1 style={styles.heading}>Microservices Lab</h1>

      <div style={styles.card}>
        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Enter some text..."
          style={styles.input}
          onKeyDown={(e) => e.key === "Enter" && handleInsert()}
        />
        <div style={styles.buttonRow}>
          <button onClick={handleInsert} disabled={loading} style={styles.button}>
            Insert
          </button>
          <button onClick={handleList} disabled={loading} style={styles.buttonSecondary}>
            List
          </button>
        </div>

        {error && <p style={styles.error}>{error}</p>}

        {hasListed && (
          <div style={styles.list}>
            {entries.length === 0 ? (
              <p style={styles.empty}>No entries yet.</p>
            ) : (
              entries.map((entry) => (
                <div key={entry.id} style={styles.listItem}>
                  <span>{entry.text}</span>
                  <span style={styles.timestamp}>
                    {new Date(entry.created_at).toLocaleString()}
                  </span>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}

const styles = {
  container: {
    fontFamily: "system-ui, sans-serif",
    maxWidth: 560,
    margin: "60px auto",
    padding: "0 20px",
  },
  heading: { fontSize: 24, marginBottom: 20 },
  card: {
    border: "1px solid #ddd",
    borderRadius: 8,
    padding: 20,
  },
  input: {
    width: "100%",
    padding: "10px 12px",
    fontSize: 15,
    boxSizing: "border-box",
    border: "1px solid #ccc",
    borderRadius: 6,
  },
  buttonRow: { display: "flex", gap: 10, marginTop: 12 },
  button: {
    padding: "8px 16px",
    fontSize: 14,
    cursor: "pointer",
    background: "#2563eb",
    color: "white",
    border: "none",
    borderRadius: 6,
  },
  buttonSecondary: {
    padding: "8px 16px",
    fontSize: 14,
    cursor: "pointer",
    background: "#f3f4f6",
    color: "#111",
    border: "1px solid #ccc",
    borderRadius: 6,
  },
  error: { color: "#dc2626", marginTop: 10, fontSize: 14 },
  list: { marginTop: 16, borderTop: "1px solid #eee", paddingTop: 12 },
  empty: { color: "#888", fontSize: 14 },
  listItem: {
    display: "flex",
    justifyContent: "space-between",
    padding: "8px 0",
    borderBottom: "1px solid #f0f0f0",
    fontSize: 14,
  },
  timestamp: { color: "#666", fontSize: 12 },
};

export default App;
