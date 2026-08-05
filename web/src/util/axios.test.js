import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import customFetch, {apiBaseUrl} from './axios';
import {addUserToLocalStorage, getUserFromLocalStorage} from './localStorage';

// axios 1.x hands the adapter an AxiosHeaders instance, but a plain object is
// possible too. Read either shape so the assertions test our interceptor and
// not axios' internal header representation.
const authHeaderOf = (config) =>
    typeof config.headers?.get === 'function'
        ? config.headers.get('Authorization')
        : config.headers?.Authorization;

const TOKEN = 'eyJhbGciOiJIUzI1NiJ9.header.signature';

describe('customFetch request interceptor', () => {
    let originalAdapter;
    let sent;

    beforeEach(() => {
        localStorage.clear();
        sent = [];
        originalAdapter = customFetch.defaults.adapter;
        customFetch.defaults.adapter = async (config) => {
            sent.push(config);
            return {
                data: {}, status: 200, statusText: 'OK', headers: {}, config,
            };
        };
    });

    afterEach(() => {
        customFetch.defaults.adapter = originalAdapter;
        localStorage.clear();
    });

    it('attaches the bearer token from localStorage to every request', async () => {
        localStorage.setItem('user', JSON.stringify({name: 'Ada', token: TOKEN}));

        await customFetch.get('event/all-events');

        expect(authHeaderOf(sent[0])).toBe(`Bearer ${TOKEN}`);
    });

    it('attaches the token on every verb, not just GET', async () => {
        localStorage.setItem('user', JSON.stringify({token: TOKEN}));

        await customFetch.post('/event/sendPdfEmail/1/2/a@b.c', {});
        await customFetch.delete('event/delete-events/abc');
        await customFetch.put('/auth/update-user/1', {});

        expect(sent).toHaveLength(3);
        for (const config of sent) {
            expect(authHeaderOf(config)).toBe(`Bearer ${TOKEN}`);
        }
    });

    it('sends no Authorization header when nobody is logged in', async () => {
        await customFetch.get('event/all-events');

        expect(authHeaderOf(sent[0])).toBeFalsy();
    });

    it('sends no Authorization header when the stored user has no token', async () => {
        localStorage.setItem('user', JSON.stringify({name: 'Ada'}));

        await customFetch.get('event/all-events');

        expect(authHeaderOf(sent[0])).toBeFalsy();
    });

    it('does not overwrite an Authorization header set by the caller', async () => {
        localStorage.setItem('user', JSON.stringify({token: TOKEN}));

        await customFetch.get('event/all-events', {
            headers: {Authorization: 'Bearer explicit-override'},
        });

        expect(authHeaderOf(sent[0])).toBe('Bearer explicit-override');
    });

    it('reads the token the login flow persisted, not a cached copy', async () => {
        // The seam that replaced the per-call `Bearer ${user.token}` spelling:
        // userSlice writes the user to localStorage, the interceptor reads it.
        addUserToLocalStorage({name: 'Ada', token: 'first-token'});
        await customFetch.get('event/all-events');

        addUserToLocalStorage({name: 'Ada', token: 'second-token'});
        await customFetch.get('event/all-events');

        expect(authHeaderOf(sent[0])).toBe('Bearer first-token');
        expect(authHeaderOf(sent[1])).toBe('Bearer second-token');
    });

    it('resolves the base URL from VITE_API_URL with no trailing slash', () => {
        expect(apiBaseUrl).toBe('http://localhost:8080');
        expect(customFetch.defaults.baseURL).toBe(apiBaseUrl);
    });
});

describe('customFetch response interceptor', () => {
    let originalAdapter;
    let assign;

    const respondWith = (status) => {
        customFetch.defaults.adapter = async (config) => {
            const error = new Error(`Request failed with status code ${status}`);
            error.config = config;
            error.response = {status, data: {msg: 'nope'}, config, headers: {}};
            throw error;
        };
    };

    let originalLocation;

    beforeEach(() => {
        localStorage.clear();
        originalAdapter = customFetch.defaults.adapter;

        // jsdom marks location.assign non-writable and non-configurable, so it
        // cannot be spied on. window.location itself is configurable, so swap
        // the whole object for the duration of the test.
        originalLocation = window.location;
        assign = vi.fn();
        Object.defineProperty(window, 'location', {
            configurable: true,
            value: {href: originalLocation.href, assign},
        });
    });

    afterEach(() => {
        customFetch.defaults.adapter = originalAdapter;
        Object.defineProperty(window, 'location', {
            configurable: true,
            value: originalLocation,
        });
        localStorage.clear();
    });

    it('logs out and redirects to /landing on 403', async () => {
        localStorage.setItem('user', JSON.stringify({token: TOKEN}));
        respondWith(403);

        await expect(customFetch.get('event/all-events')).rejects.toThrow();

        expect(getUserFromLocalStorage()).toBeNull();
        expect(assign).toHaveBeenCalledWith('/landing');
    });

    it('leaves the session alone on a non-403 failure', async () => {
        localStorage.setItem('user', JSON.stringify({token: TOKEN}));
        respondWith(500);

        await expect(customFetch.get('event/all-events')).rejects.toThrow();

        expect(getUserFromLocalStorage()).toEqual({token: TOKEN});
        expect(assign).not.toHaveBeenCalled();
    });

    it('rejects with the original error when the request never got a response', async () => {
        localStorage.setItem('user', JSON.stringify({token: TOKEN}));
        customFetch.defaults.adapter = async () => {
            throw new Error('Network Error');
        };

        // Regression guard: reading `error.response.status` unguarded threw a
        // TypeError here and masked the real network failure.
        await expect(customFetch.get('event/all-events'))
            .rejects.toThrow('Network Error');

        expect(getUserFromLocalStorage()).toEqual({token: TOKEN});
        expect(assign).not.toHaveBeenCalled();
    });
});
