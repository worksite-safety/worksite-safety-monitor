import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {cleanup, render, screen} from '@testing-library/react';
import {configureStore} from '@reduxjs/toolkit';
import {Provider} from 'react-redux';

// Smoke tests for the build-tooling migration: these boot the real reducer, the
// real router and the styled-components wrappers, so they fail loudly if the
// Redux Toolkit, React Router or Vite/JSX wiring regresses. Nothing here talks
// to the engine.
vi.mock('react-toastify', () => ({
    toast: {success: vi.fn(), error: vi.fn()},
    ToastContainer: () => null,
}));

import App from './App';
import userReducer from './features/user/userSlice';

// App reads the store through useSelector but never imports it, so a per-test
// store with a preloaded slice keeps these cases independent of localStorage.
const renderApp = (user = null) => {
    const store = configureStore({
        reducer: {user: userReducer},
        preloadedState: {user: {isLoading: false, isSidebarOpen: false, user}},
    });
    return render(<Provider store={store}><App/></Provider>);
};

beforeEach(() => {
    localStorage.clear();
    window.history.pushState({}, '', '/');
});

afterEach(() => {
    cleanup();
    localStorage.clear();
});

describe('App', () => {
    it('renders the landing page for a logged-out visitor', () => {
        renderApp(null);

        expect(screen.getByRole('heading', {name: /Worksite AI Guardian/i}))
            .toBeInTheDocument();
        expect(screen.getByRole('link', {name: /Login\/Register/i}))
            .toBeInTheDocument();
    });

    it('keeps the dashboard out of reach for a user without the ADMIN role', () => {
        renderApp({name: 'Ada', role: 'VIEWER', token: 'a.b.c'});

        // App gates the whole authenticated route tree on role === 'ADMIN', so
        // a non-admin falls through to the public landing route.
        expect(screen.getByRole('heading', {name: /Worksite AI Guardian/i}))
            .toBeInTheDocument();
    });

    it('renders the not-found page for an unknown route', () => {
        window.history.pushState({}, '', '/no-such-page');

        renderApp(null);

        expect(screen.getByRole('heading', {name: /Page Not Found/i}))
            .toBeInTheDocument();
    });

    // The footer is mounted outside <Routes> precisely so that no route can be
    // reached without it. AGPL section 13 owes the source offer to whoever
    // interacts with the program over a network, which includes a visitor who
    // has not logged in and one who mistyped the URL -- so both are checked.
    it('offers the source to a visitor who has not logged in', () => {
        renderApp(null);

        expect(screen.getByRole('link', {name: /source code/i}))
            .toHaveAttribute('href', 'https://github.com/worksite-safety/worksite-safety-monitor');
    });

    it('offers the source on the not-found page too', () => {
        window.history.pushState({}, '', '/no-such-page');

        renderApp(null);

        expect(screen.getByRole('link', {name: /source code/i})).toBeInTheDocument();
    });

    it('warns a logged-out visitor that the system is not certified', () => {
        renderApp(null);

        expect(screen.getByText(/not a certified safety system/i)).toBeInTheDocument();
    });

    it('no longer claims the landing page protects lives', () => {
        renderApp(null);

        // The old tagline was "Protecting Lives, One Frame at a Time". Fall
        // detection scores mAP@0.5 = 0.589 and neither gesture detector has
        // ever fired on real footage, so the claim was not one the measurements
        // supported. This case is here to stop it drifting back.
        expect(screen.queryByText(/protecting lives/i)).not.toBeInTheDocument();
    });
});
