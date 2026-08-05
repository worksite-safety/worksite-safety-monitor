import axios from "axios";
import {clearStore} from "../features/user/userSlice";
import {getUserFromLocalStorage, removeUserFromLocalStorage} from "./localStorage";

// Configured at build time via .env (see .env.example). The fallback keeps a
// plain `npm run dev` working against a local engine with no setup.
const DEFAULT_API_URL = 'http://localhost:8080';

export const apiBaseUrl = String(
    import.meta.env.VITE_API_URL || DEFAULT_API_URL
).replace(/\/+$/, '');

const customFetch = axios.create({
    baseURL: apiBaseUrl
})

// Every authenticated call used to spell out its own
// `headers: { Authorization: `Bearer ${user.token}` }`, so each new call site
// could forget it. localStorage is the single source of truth for the token:
// userSlice writes it there on login/register/update and clears it on logout,
// so reading it here cannot go stale. Importing the store instead would create
// a cycle (store -> userSlice -> axios -> store).
customFetch.interceptors.request.use((config) => {
    const token = getUserFromLocalStorage()?.token;
    if (token && !config.headers.Authorization) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

export const checkForUnauthorizedResponse = (error, thunkAPI) => {
    if (error.response.status === 403) {
        thunkAPI.dispatch(clearStore());
        return thunkAPI.rejectWithValue('Unauthorized! Logging Out...');
    }
    return thunkAPI.rejectWithValue(error.response.data.msg);
};

customFetch.interceptors.response.use(
    (response) => response,
    (error) => {
        // Unchanged behaviour: the engine answers 403 for an expired, forged or
        // missing token, so 403 is treated as "the session is over". The
        // optional chaining is new -- a network failure has no `error.response`,
        // and the old `error.response.status` threw a TypeError that replaced
        // the real error with a confusing one.
        if (error.response?.status === 403) {
            removeUserFromLocalStorage();
            window.location.assign("/landing");
        }
        return Promise.reject(error);
    }
);

export default customFetch;
