import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {
    cleanup,
    fireEvent,
    render,
    screen,
    waitFor,
    within,
} from '@testing-library/react';
import {configureStore} from '@reduxjs/toolkit';
import {Provider} from 'react-redux';

// The date picker and the toast container belong to other parts of the page;
// stubbing them keeps this about the grid.
vi.mock('../components/DatePickerComp', () => ({default: () => null}));
vi.mock('react-toastify', () => ({toast: {success: vi.fn(), error: vi.fn()}}));
vi.mock('../util/axios', () => ({
    default: {get: vi.fn(), post: vi.fn(), delete: vi.fn()},
    checkForUnauthorizedResponse: vi.fn(),
}));

import Reporting from './Reporting';
import customFetch from '../util/axios';
import userReducer from '../features/user/userSlice';

// Midday UTC, so the formatted dd/MM/yyyy is the same calendar day in every
// timezone this is likely to run in. The suite deliberately does not pin one.
const at = (iso) => new Date(iso).getTime();

const EVENTS = [
    {
        id: '1',
        eventType: 'FALL',
        startTime: at('2024-01-02T12:00:00Z'),
        confidencePercentage: 0.874,
        timePeriod: null,
        cameraName: 'gate',
    },
    {
        id: '2',
        eventType: 'NO_HELMET',
        startTime: at('2023-12-11T12:00:00Z'),
        confidencePercentage: 0.64,
        timePeriod: 42,
        cameraName: 'yard',
    },
    {
        id: '3',
        eventType: 'ARMS_UP',
        startTime: at('2024-01-05T12:00:00Z'),
        confidencePercentage: 0.91,
        timePeriod: null,
        cameraName: 'gate',
    },
];

const renderPage = () => {
    const store = configureStore({
        reducer: {user: userReducer},
        preloadedState: {
            user: {
                isLoading: false,
                isSidebarOpen: false,
                user: {name: 'Ada', email: 'ada@example.com', token: 'a.b.c'},
            },
        },
    });
    return render(<Provider store={store}><Reporting/></Provider>);
};

const bodyRows = () => screen.getAllByRole('row').slice(1);

beforeEach(() => {
    customFetch.get.mockResolvedValue({data: EVENTS});
    customFetch.delete.mockResolvedValue({status: 200});
});

afterEach(() => {
    cleanup();
});

describe('Reporting', () => {
    it('shows the events the engine returns, formatted', async () => {
        renderPage();

        await waitFor(() => expect(bodyRows()).toHaveLength(3));

        expect(screen.getAllByRole('columnheader').map((th) => th.textContent))
            .toEqual([
                'Event Type', 'Start Time', 'Confidence Percentage',
                'Time Period', 'Camera Name', 'Actions',
            ]);
        // 0.874 -> '87%', and a null timePeriod -> '-'.
        expect(screen.getByText('87%')).toBeInTheDocument();
        expect(screen.getAllByText('-')).toHaveLength(2);
    });

    it('opens sorted by startTime descending, comparing it as text', async () => {
        renderPage();

        await waitFor(() => expect(bodyRows()).toHaveLength(3));

        // startTime is already a dd/MM/yyyy string when it reaches the grid, so
        // "11/12/2023" sorts above "05/01/2024". Chronologically wrong, and the
        // order this page has always opened in.
        expect(bodyRows().map(
            (row) => within(row).getAllByRole('cell')[0].textContent))
            .toEqual(['NO_HELMET', 'ARMS_UP', 'FALL']);
    });

    it('deletes the row the icon belongs to', async () => {
        renderPage();

        await waitFor(() => expect(bodyRows()).toHaveLength(3));

        // Last row on screen is FALL, id 1, because of the text sort above.
        const row = bodyRows()[2];
        fireEvent.click(within(row).getByRole('button', {name: 'Delete'}));

        await waitFor(() => expect(customFetch.delete)
            .toHaveBeenCalledWith('event/delete-events/1'));
    });

    it('names the CSV export reportLocalExport', async () => {
        const blobs = [];
        const downloads = [];
        URL.createObjectURL = vi.fn((blob) => {
            blobs.push(blob);
            return 'blob:test';
        });
        URL.revokeObjectURL = vi.fn();
        vi.spyOn(HTMLAnchorElement.prototype, 'click')
            .mockImplementation(function click() {
                downloads.push(this.download);
            });

        try {
            renderPage();
            await waitFor(() => expect(bodyRows()).toHaveLength(3));

            fireEvent.click(screen.getByRole('button', {name: /export/i}));
            fireEvent.click(
                screen.getByRole('menuitem', {name: 'Download as CSV'}));

            expect(downloads).toEqual(['reportLocalExport.csv']);
        } finally {
            delete URL.createObjectURL;
            delete URL.revokeObjectURL;
        }
    });
});
