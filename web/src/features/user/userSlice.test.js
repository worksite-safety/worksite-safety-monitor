import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

// The slice fires toasts as a side effect of its reducers; keep them out of the
// assertions but make sure they are still reached.
vi.mock('react-toastify', () => ({
    toast: {
        success: vi.fn(),
        error: vi.fn(),
    },
}));

import {toast} from 'react-toastify';
import reducer, {
    loginUser,
    logoutUser,
    registerUser,
    toggleSidebar,
    updateUser,
} from './userSlice';

const STORED_USER = {
    id: '65f0',
    name: 'Ada',
    lastName: 'Lovelace',
    email: 'ada@example.com',
    role: 'ADMIN',
    token: 'a.jwt.token',
};

const initial = () => reducer(undefined, {type: '@@INIT'});

beforeEach(() => {
    localStorage.clear();
});

afterEach(() => {
    localStorage.clear();
});

describe('rehydrating the session from localStorage', () => {
    // initialState is evaluated when the module is first imported, so these
    // cases have to seed localStorage and then re-import the module.
    const freshSlice = async () => {
        vi.resetModules();
        return (await import('./userSlice')).default;
    };

    it('starts logged in when a user was persisted', async () => {
        localStorage.setItem('user', JSON.stringify(STORED_USER));

        const freshReducer = await freshSlice();

        expect(freshReducer(undefined, {type: '@@INIT'}).user).toEqual(STORED_USER);
    });

    it('starts logged out when nothing was persisted', async () => {
        const freshReducer = await freshSlice();

        expect(freshReducer(undefined, {type: '@@INIT'}).user).toBeNull();
    });

    it('starts logged out rather than crashing on corrupt storage', async () => {
        // The request interceptor now reads localStorage on every call, so a
        // throw here would break every request, not just the initial boot.
        localStorage.setItem('user', '{not valid json');

        const freshReducer = await freshSlice();

        expect(freshReducer(undefined, {type: '@@INIT'}).user).toBeNull();
    });

    it('boots with the sidebar closed and not loading', async () => {
        const freshReducer = await freshSlice();
        const state = freshReducer(undefined, {type: '@@INIT'});

        expect(state.isLoading).toBe(false);
        expect(state.isSidebarOpen).toBe(false);
    });
});

describe('synchronous reducers', () => {
    it('toggleSidebar flips the flag both ways', () => {
        const opened = reducer(initial(), toggleSidebar());
        expect(opened.isSidebarOpen).toBe(true);

        expect(reducer(opened, toggleSidebar()).isSidebarOpen).toBe(false);
    });

    it('logoutUser clears the user, closes the sidebar and wipes storage', () => {
        localStorage.setItem('user', JSON.stringify(STORED_USER));
        const loggedIn = {isLoading: false, isSidebarOpen: true, user: STORED_USER};

        const state = reducer(loggedIn, logoutUser());

        expect(state.user).toBeNull();
        expect(state.isSidebarOpen).toBe(false);
        expect(localStorage.getItem('user')).toBeNull();
    });
});

// The object-map extraReducers form this slice used to have was removed in
// Redux Toolkit 2.x: it does not throw, it just silently stops matching, so
// every one of these cases would have gone unnoticed.
describe.each([
    ['loginUser', loginUser],
    ['registerUser', registerUser],
    ['updateUser', updateUser],
])('%s lifecycle', (_name, thunk) => {
    it('sets isLoading on pending', () => {
        const state = reducer(initial(), {type: thunk.pending.type});

        expect(state.isLoading).toBe(true);
    });

    it('stores the user and persists it on fulfilled', () => {
        const state = reducer(
            {...initial(), isLoading: true},
            {type: thunk.fulfilled.type, payload: {user: STORED_USER}},
        );

        expect(state.isLoading).toBe(false);
        expect(state.user).toEqual(STORED_USER);
        expect(JSON.parse(localStorage.getItem('user'))).toEqual(STORED_USER);
        expect(toast.success).toHaveBeenCalled();
    });

    it('clears isLoading and surfaces the message on rejected', () => {
        const state = reducer(
            {...initial(), isLoading: true},
            {type: thunk.rejected.type, payload: 'Unauthorized! Logging Out...'},
        );

        expect(state.isLoading).toBe(false);
        expect(state.user).toBeNull();
        expect(toast.error).toHaveBeenCalledWith('Unauthorized! Logging Out...');
    });

    it('does not touch storage while pending', () => {
        reducer(initial(), {type: thunk.pending.type});

        expect(localStorage.getItem('user')).toBeNull();
    });
});
