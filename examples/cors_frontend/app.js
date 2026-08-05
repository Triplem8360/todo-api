"use strict";

const API_ORIGIN = "http://localhost:8000";
const API_BASE_URL = `${API_ORIGIN}/api/v1`;

const CSRF_COOKIE_NAME = "todo_csrf_token";
const CSRF_HEADER_NAME = "X-CSRF-Token";

const outputElement = document.querySelector("#output");
const metadataElement = document.querySelector("#metadata");

document.querySelector("#frontend-origin").textContent =
    window.location.origin;

function readCookie(name) {
    const encodedName = `${encodeURIComponent(name)}=`;

    const cookie = document.cookie
        .split("; ")
        .find((item) => item.startsWith(encodedName));

    if (!cookie) {
        return null;
    }

    return decodeURIComponent(cookie.slice(encodedName.length));
}

function isUnsafeMethod(method) {
    return !["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase());
}

function showResult(data) {
    outputElement.textContent = JSON.stringify(data, null, 2);
}

function showError(error) {
    outputElement.textContent =
        error instanceof Error ? error.message : String(error);
}

function showMetadata(response) {
    const processTime = response.headers.get("X-Process-Time");
    const requestId = response.headers.get("X-Request-ID");

    metadataElement.textContent = [
        `Status: ${response.status}`,
        `X-Process-Time: ${processTime ?? "not exposed"}`,
        `X-Request-ID: ${requestId ?? "not exposed"}`,
    ].join("\n");
}

async function parseResponse(response) {
    const text = await response.text();

    if (!text) {
        return null;
    }

    const contentType = response.headers.get("content-type") ?? "";

    if (contentType.includes("application/json")) {
        return JSON.parse(text);
    }

    return text;
}

async function apiFetch(path, options = {}) {
    const method = (options.method ?? "GET").toUpperCase();
    const headers = new Headers(options.headers ?? {});

    if (options.body && !headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json");
    }

    if (isUnsafeMethod(method)) {
        const csrfToken = readCookie(CSRF_COOKIE_NAME);

        if (csrfToken) {
            headers.set(CSRF_HEADER_NAME, csrfToken);
        }
    }

    const response = await fetch(`${API_BASE_URL}${path}`, {
        ...options,
        method,
        headers,

        // Required for cross-origin cookies and Set-Cookie responses.
        credentials: "include",
    });

    showMetadata(response);

    const data = await parseResponse(response);

    if (!response.ok) {
        throw new Error(
            `HTTP ${response.status}\n${JSON.stringify(data, null, 2)}`,
        );
    }

    showResult(data ?? { status: "success" });

    return data;
}

async function runRequest(callback) {
    try {
        outputElement.textContent = "Loading...";
        await callback();
    } catch (error) {
        console.error(error);
        showError(error);
    }
}

document
    .querySelector("#health-button")
    .addEventListener("click", () => {
        runRequest(() => apiFetch("/health"));
    });

document
    .querySelector("#docs-button")
    .addEventListener("click", () => {
        runRequest(() => fetch(`${API_ORIGIN}/openapi.json`, {
            credentials: "include",
        }).then(async (response) => {
            showMetadata(response);

            const data = await parseResponse(response);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            showResult(data);
        }));
    });

document
    .querySelector("#login-form")
    .addEventListener("submit", (event) => {
        event.preventDefault();

        const username = document.querySelector("#username").value;
        const password = document.querySelector("#password").value;

        const formData = new URLSearchParams({
            username,
            password,
        });

        runRequest(() => apiFetch("/auth/browser/login", {
            method: "POST",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded",
            },
            body: formData,
        }));
    });

document
    .querySelector("#profile-button")
    .addEventListener("click", () => {
        runRequest(() => apiFetch("/users/me"));
    });

document
    .querySelector("#todos-button")
    .addEventListener("click", () => {
        runRequest(() => apiFetch("/todos"));
    });

document
    .querySelector("#refresh-button")
    .addEventListener("click", () => {
        runRequest(() => apiFetch("/auth/browser/refresh", {
            method: "POST",
        }));
    });

document
    .querySelector("#logout-button")
    .addEventListener("click", () => {
        runRequest(() => apiFetch("/auth/browser/logout", {
            method: "POST",
        }));
    });