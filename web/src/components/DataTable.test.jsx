import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {act, cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {createColumnHelper} from '@tanstack/react-table';

import DataTable from './DataTable';

// These cases exist to pin the behaviour the MUI DataGrid gave this page, not
// to describe TanStack Table. Where a number or an ordering below looks
// arbitrary it was read off the DataGrid v6.20.4 source that used to run here:
// the 100-row page, the ['asc', 'desc', null] sort cycle, the 500 ms quick
// filter debounce, the CSV quoting rules. Changing one of them changes what
// the Reporting page does, so change the assertion only with that in mind.

const columnHelper = createColumnHelper();

const FIELDS = {
    eventType: 'Event Type',
    startTime: 'Start Time',
    confidencePercentage: 'Confidence Percentage',
    timePeriod: 'Time Period',
    cameraName: 'Camera Name',
};

const makeColumns = (onDelete = vi.fn()) => [
    ...Object.entries(FIELDS).map(([field, header]) =>
        columnHelper.accessor(field, {id: field, header})),
    columnHelper.display({
        id: 'actions',
        header: 'Actions',
        cell: ({row}) => (
            <span role="button" aria-label="Delete"
                  onClick={() => onDelete(row.original.id)}/>
        ),
    }),
];

// Rows arrive from Reporting already formatted: `startTime` is a
// `toLocaleString('en-GB')` string, `confidencePercentage` a string, and
// `timePeriod` either a number or '-'.
const ROWS = [
    {
        id: '1',
        eventType: 'FALL',
        startTime: '02/01/2024, 09:00:00',
        confidencePercentage: '87%',
        timePeriod: '-',
        cameraName: 'gate',
    },
    {
        id: '2',
        eventType: 'NO_HELMET',
        startTime: '11/12/2023, 17:30:00',
        confidencePercentage: '64%',
        timePeriod: 4200,
        cameraName: 'yard',
    },
    {
        id: '3',
        eventType: 'ARMS_UP',
        startTime: '05/01/2024, 08:15:00',
        confidencePercentage: '91%',
        timePeriod: '-',
        cameraName: 'gate',
    },
];

const renderTable = (props = {}) => render(
    <DataTable rows={ROWS} columns={makeColumns()} {...props}/>);

const bodyRows = () => screen.getAllByRole('row').slice(1);

const firstCells = () => bodyRows().map(
    (row) => within(row).getAllByRole('cell')[0].textContent);

afterEach(() => {
    cleanup();
});

describe('DataTable', () => {
    it('renders the six reporting columns in order', () => {
        renderTable();

        expect(screen.getAllByRole('columnheader').map((th) => th.textContent))
            .toEqual([
                'Event Type', 'Start Time', 'Confidence Percentage',
                'Time Period', 'Camera Name', 'Actions',
            ]);
    });

    it('renders a row per event', () => {
        renderTable();

        expect(bodyRows()).toHaveLength(3);
        expect(screen.getByText('11/12/2023, 17:30:00')).toBeInTheDocument();
        // A null timePeriod reaches the grid as '-'.
        expect(screen.getAllByText('-')).toHaveLength(2);
    });

    it('sorts startTime as text, the way the old grid did', () => {
        // `startTime` is a formatted dd/MM/yyyy string by the time it gets
        // here, and the DataGrid compared it with Intl.Collator. Descending
        // therefore puts 11/12/2023 first -- lexically largest, chronologically
        // oldest. This is a defect being preserved, not a result: the fix
        // belongs in whatever stops formatting the value before sorting it.
        renderTable({sorting: [{id: 'startTime', desc: true}]});

        expect(firstCells()).toEqual(['NO_HELMET', 'ARMS_UP', 'FALL']);
    });

    it('cycles a header through asc, desc and unsorted', () => {
        const onSortingChange = vi.fn();
        let sorting = [];
        const {rerender} = render(
            <DataTable rows={ROWS} columns={makeColumns()} sorting={sorting}
                       onSortingChange={onSortingChange}/>);

        const apply = (updater) => {
            sorting = typeof updater === 'function' ? updater(sorting) : updater;
            rerender(<DataTable rows={ROWS} columns={makeColumns()}
                                sorting={sorting}
                                onSortingChange={onSortingChange}/>);
        };

        const header = () => within(screen.getAllByRole('columnheader')[0])
            .getByRole('button');

        fireEvent.click(header());
        apply(onSortingChange.mock.calls[0][0]);
        // Ascending first even for a column of numbers, because the DataGrid's
        // sortingOrder was ['asc', 'desc', null] for every column type.
        expect(sorting).toEqual([{id: 'eventType', desc: false}]);

        fireEvent.click(header());
        apply(onSortingChange.mock.calls[1][0]);
        expect(sorting).toEqual([{id: 'eventType', desc: true}]);

        fireEvent.click(header());
        apply(onSortingChange.mock.calls[2][0]);
        expect(sorting).toEqual([]);
    });

    it('leaves the actions column unsortable', () => {
        renderTable();

        const actions = screen.getAllByRole('columnheader')[5];
        expect(within(actions).queryByRole('button')).not.toBeInTheDocument();
    });

    it('calls the delete handler with the row id', () => {
        const onDelete = vi.fn();
        render(<DataTable rows={ROWS} columns={makeColumns(onDelete)}
                          getRowId={(row) => row.id}/>);

        fireEvent.click(screen.getAllByRole('button', {name: 'Delete'})[1]);

        expect(onDelete).toHaveBeenCalledWith('2');
    });

    it('shows the loading overlay while loading', () => {
        renderTable({loading: true});

        expect(screen.getByRole('progressbar')).toBeInTheDocument();
        expect(screen.queryByText('No rows')).not.toBeInTheDocument();
    });

    it('shows "No rows" for an empty, settled grid', () => {
        render(<DataTable rows={[]} columns={makeColumns()}/>);

        expect(screen.getByText('No rows')).toBeInTheDocument();
    });

    describe('quick filter', () => {
        beforeEach(() => {
            vi.useFakeTimers();
        });

        afterEach(() => {
            vi.useRealTimers();
        });

        const type = (value) => fireEvent.change(
            screen.getByRole('searchbox', {name: 'Search'}),
            {target: {value}});

        it('waits 500 ms before filtering', () => {
            renderTable();

            type('yard');
            act(() => vi.advanceTimersByTime(499));
            expect(bodyRows()).toHaveLength(3);

            act(() => vi.advanceTimersByTime(1));
            expect(firstCells()).toEqual(['NO_HELMET']);
        });

        it('searches every column, case insensitively', () => {
            renderTable();

            type('fall');
            act(() => vi.advanceTimersByTime(500));
            expect(firstCells()).toEqual(['FALL']);

            type('91%');
            act(() => vi.advanceTimersByTime(500));
            expect(firstCells()).toEqual(['ARMS_UP']);
        });

        it('requires every space-separated term, from any column', () => {
            renderTable();

            // The DataGrid's quick filter split on spaces and AND-ed the
            // terms, matching each one against any column.
            type('arms gate');
            act(() => vi.advanceTimersByTime(500));
            expect(firstCells()).toEqual(['ARMS_UP']);

            type('arms yard');
            act(() => vi.advanceTimersByTime(500));
            expect(bodyRows()).toHaveLength(0);
        });

        it('clears without waiting for the debounce', () => {
            renderTable();

            type('yard');
            act(() => vi.advanceTimersByTime(500));
            expect(bodyRows()).toHaveLength(1);

            fireEvent.click(screen.getByRole('button', {name: 'Clear'}));
            expect(bodyRows()).toHaveLength(3);
        });
    });

    describe('pagination', () => {
        const many = Array.from({length: 120}, (_, index) => ({
            id: String(index),
            eventType: `EVENT_${String(index).padStart(3, '0')}`,
            startTime: '02/01/2024, 09:00:00',
            confidencePercentage: '10%',
            timePeriod: index,
            cameraName: 'gate',
        }));

        it('shows 100 rows a page, as the DataGrid did', () => {
            render(<DataTable rows={many} columns={makeColumns()}
                              getRowId={(row) => row.id}/>);

            expect(bodyRows()).toHaveLength(100);
            expect(screen.getByText('1–100 of 120')).toBeInTheDocument();
        });

        it('pages forward and back', () => {
            render(<DataTable rows={many} columns={makeColumns()}
                              getRowId={(row) => row.id}/>);

            fireEvent.click(screen.getByRole('button', {name: /next page/i}));
            expect(bodyRows()).toHaveLength(20);
            expect(screen.getByText('101–120 of 120')).toBeInTheDocument();

            fireEvent.click(
                screen.getByRole('button', {name: /previous page/i}));
            expect(screen.getByText('1–100 of 120')).toBeInTheDocument();
        });

        it('offers the DataGrid page sizes', () => {
            render(<DataTable rows={many} columns={makeColumns()}
                              getRowId={(row) => row.id}/>);

            const select = screen.getByRole('combobox');
            expect(Array.from(select.options).map((option) => option.value))
                .toEqual(['25', '50', '100']);

            fireEvent.change(select, {target: {value: '25'}});
            expect(bodyRows()).toHaveLength(25);
        });
    });

    describe('export', () => {
        let blobs;
        let downloads;

        beforeEach(() => {
            blobs = [];
            downloads = [];
            URL.createObjectURL = vi.fn((blob) => {
                blobs.push(blob);
                return 'blob:test';
            });
            URL.revokeObjectURL = vi.fn();
            vi.spyOn(HTMLAnchorElement.prototype, 'click')
                .mockImplementation(function click() {
                    downloads.push(this.download);
                });
        });

        afterEach(() => {
            delete URL.createObjectURL;
            delete URL.revokeObjectURL;
        });

        const openMenu = () => fireEvent.click(
            screen.getByRole('button', {name: /export/i}));

        it('downloads reportLocalExport.csv', async () => {
            renderTable({exportFileName: 'reportLocalExport'});

            openMenu();
            fireEvent.click(screen.getByRole('menuitem', {name: 'Download as CSV'}));

            expect(downloads).toEqual(['reportLocalExport.csv']);
            const csv = await blobs[0].text();
            const lines = csv.split('\r\n');
            expect(lines[0]).toBe(
                'Event Type,Start Time,Confidence Percentage,Time Period,Camera Name,Actions');
            // The DataGrid quoted a value only when it held the delimiter, a
            // quote or a newline -- startTime holds a comma -- and prefixed a
            // value starting like a formula, which is why '-' leaves as '-.
            expect(lines[1]).toBe('FALL,"02/01/2024, 09:00:00",87%,\'-,gate,');
            expect(lines[2]).toBe(
                'NO_HELMET,"11/12/2023, 17:30:00",64%,4200,yard,');
        });

        it('exports the filtered and sorted rows, not the page', async () => {
            vi.useFakeTimers();
            try {
                renderTable({
                    exportFileName: 'reportLocalExport',
                    sorting: [{id: 'eventType', desc: false}],
                });

                fireEvent.change(
                    screen.getByRole('searchbox', {name: 'Search'}),
                    {target: {value: 'gate'}});
                act(() => vi.advanceTimersByTime(500));

                openMenu();
                fireEvent.click(
                    screen.getByRole('menuitem', {name: 'Download as CSV'}));
            } finally {
                vi.useRealTimers();
            }

            const csv = await blobs[0].text();
            expect(csv.split('\r\n').map((line) => line.split(',')[0]))
                .toEqual(['Event Type', 'ARMS_UP', 'FALL']);
        });
    });

    describe('print', () => {
        let printedRowCount;
        let originalPrint;

        beforeEach(() => {
            printedRowCount = null;
            originalPrint = window.print;
            window.print = vi.fn(() => {
                printedRowCount = document.querySelectorAll('tbody tr').length;
            });
        });

        afterEach(() => {
            window.print = originalPrint;
        });

        it('prints every row, not just the page on screen', () => {
            const many = Array.from({length: 120}, (_, index) => ({
                id: String(index),
                eventType: 'FALL',
                startTime: '02/01/2024, 09:00:00',
                confidencePercentage: '10%',
                timePeriod: index,
                cameraName: 'gate',
            }));
            render(<DataTable rows={many} columns={makeColumns()}
                              getRowId={(row) => row.id}/>);

            fireEvent.click(screen.getByRole('button', {name: /export/i}));
            fireEvent.click(screen.getByRole('menuitem', {name: 'Print'}));

            expect(window.print).toHaveBeenCalled();
            expect(printedRowCount).toBe(120);
            // ...and the grid goes back to its page afterwards.
            expect(bodyRows()).toHaveLength(100);
        });
    });
});
