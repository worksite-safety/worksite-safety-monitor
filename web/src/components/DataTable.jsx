import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {createGlobalStyle} from 'styled-components';
import {
  columnFilteringFeature,
  createFilteredRowModel,
  createPaginatedRowModel,
  createSortedRowModel,
  globalFilteringFeature,
  rowPaginationFeature,
  rowSortingFeature,
  tableFeatures,
  useTable,
} from '@tanstack/react-table';
import {
  MdClose,
  MdKeyboardArrowLeft,
  MdKeyboardArrowRight,
  MdSaveAlt,
  MdSearch,
  MdArrowUpward,
} from 'react-icons/md';
import Wrapper from '../assets/wrappers/DataTable';

// TanStack Table v9 registers features explicitly: an API that is not
// registered here does not exist on the instance. Row-model factories are
// feature slots, not table options, and each one sits after the feature it
// needs (filteredRowModel after columnFilteringFeature, and so on).
const features = tableFeatures({
  columnFilteringFeature,
  globalFilteringFeature,
  rowSortingFeature,
  rowPaginationFeature,
  filteredRowModel: createFilteredRowModel(),
  sortedRowModel: createSortedRowModel(),
  paginatedRowModel: createPaginatedRowModel(),
});

// Ported from @mui/x-data-grid v6.20.4's `gridStringOrNumberComparator` (plus
// its nil handling), because the grid this replaces sorted with it and the
// column values are pre-formatted strings. `startTime` in particular arrives
// as "dd/MM/yyyy, HH:mm:ss" and is therefore compared as text, not as a date.
// That is the sort order the page has always had; reproducing the comparator
// is what keeps it identical.
const collator = new Intl.Collator();

const compareValues = (a, b) => {
  if (a == null && b != null) {
    return -1;
  }
  if (b == null && a != null) {
    return 1;
  }
  if (a == null && b == null) {
    return 0;
  }
  if (typeof a === 'string') {
    return collator.compare(a.toString(), b.toString());
  }
  return a - b;
};

const gridSortFn = (rowA, rowB, columnId) =>
    compareValues(rowA.getValue(columnId), rowB.getValue(columnId));

const defaultColumn = {sortFn: gridSortFn};

// MUI's quick filter splits the box on spaces and requires *every* term to
// match *some* column (its default AND logic operator), so "fall camera-1"
// matches a row whose event type is FALL and whose camera is camera-1. A
// per-column `includesString` cannot express that, but a v9 filter function
// receives the whole row, so this evaluates the row once and returns the same
// answer for whichever column the filtered row model asks about -- the model
// ORs the columns together and stops at the first `true`.
const quickFilterFn = (row, _columnId, filterValue) => {
  const terms = String(filterValue ?? '').split(' ').filter(Boolean);
  if (terms.length === 0) {
    return true;
  }
  const cells = row.table
      .getAllLeafColumns()
      .filter((column) => !!column.accessorFn)
      .map((column) => String(row.getValue(column.id) ?? '').toLowerCase());

  return terms.every(
      (term) => cells.some((cell) => cell.includes(term.toLowerCase())));
};

// Also ported from the DataGrid: quote only when the value would otherwise
// break the row, and prefix a value that starts like a spreadsheet formula.
// The visible consequence is that a '-' cell exports as '- , which is what the
// old export produced and what CSV injection guidance asks for.
const FORMULA_STARTS = ['=', '+', '-', '@', '\t', '\r'];

const serialiseCsvValue = (value, delimiter) => {
  if (typeof value !== 'string') {
    return value;
  }
  const escaped = value.replace(/"/g, '""');
  if ([delimiter, '\n', '\r', '"'].some((token) => value.includes(token))) {
    return `"${escaped}"`;
  }
  if (FORMULA_STARTS.includes(escaped[0])) {
    return `'${escaped}`;
  }
  return escaped;
};

const headerText = (column) => typeof column.columnDef.header === 'string'
    ? column.columnDef.header
    : column.id;

const buildCsv = (columns, rows, delimiter = ',') => {
  const serialiseRow = (values) => values
      .map((value) => (value === null || value === undefined)
          ? ''
          : serialiseCsvValue(value, delimiter))
      .join(delimiter);

  const head = serialiseRow(columns.map((column) => headerText(column)));
  const body = rows
      .map((row) => serialiseRow(columns.map(
          // A display column (Actions) has no accessor and so no value; the
          // old export wrote an empty cell under its header, not no column.
          (column) => column.accessorFn ? row.getValue(column.id) : undefined)))
      .join('\r\n');

  return `${head}\r\n${body}`.trim();
};

const downloadCsv = (csv, fileName) => {
  const blob = new Blob([csv], {type: 'text/csv'});
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `${fileName}.csv`;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url));
};

// Printing used to clone the grid into an off-screen iframe, so the printed
// page held the table and nothing else, with every row on it and without the
// toolbar or the footer. Hiding the rest of the page for the duration of the
// print gets to the same output without a second React tree.
const PrintStyle = createGlobalStyle`
  @media print {
    body * {
      visibility: hidden !important;
    }
    .data-table-print-root,
    .data-table-print-root * {
      visibility: visible !important;
    }
    .data-table-print-root {
      position: absolute !important;
      top: 0;
      left: 0;
      width: 100%;
      height: auto !important;
      border: none;
    }
    .data-table-print-root .data-table-toolbar,
    .data-table-print-root .data-table-footer {
      display: none !important;
    }
    .data-table-print-root .data-table-main {
      overflow: visible !important;
    }
  }
`;

const DataTable = ({
  columns,
  rows,
  loading = false,
  sorting,
  onSortingChange,
  getRowId,
  exportFileName = 'export',
  initialPageSize = 100,
  pageSizeOptions = [25, 50, 100],
  searchDebounceMs = 500,
}) => {
  const [internalSorting, setInternalSorting] = useState([]);
  const [searchValue, setSearchValue] = useState('');
  const [globalFilter, setGlobalFilter] = useState('');
  const [pagination, setPagination] = useState(
      {pageIndex: 0, pageSize: initialPageSize});
  const [menuOpen, setMenuOpen] = useState(false);
  const [printing, setPrinting] = useState(false);
  const debounceRef = useRef(null);
  const exportRef = useRef(null);

  // Every row has to be on the page while the print dialog is open, the way
  // the old print export re-rowed its clone before printing it.
  const printPagination = useMemo(
      () => ({pageIndex: 0, pageSize: Math.max(rows.length, 1)}),
      [rows.length]);
  const activePagination = printing ? printPagination : pagination;

  const table = useTable({
    features,
    columns,
    data: rows,
    defaultColumn,
    getRowId,
    globalFilterFn: quickFilterFn,
    // The community DataGrid forced `disableMultipleColumnsSorting` and cycled
    // asc -> desc -> unsorted from `sortingOrder`. v9 would otherwise start a
    // numeric column at desc, so pin the first direction rather than let it be
    // inferred from the data.
    enableMultiSort: false,
    sortDescFirst: false,
    state: {
      sorting: sorting ?? internalSorting,
      globalFilter,
      pagination: activePagination,
    },
    onSortingChange: onSortingChange ?? setInternalSorting,
    onGlobalFilterChange: setGlobalFilter,
    onPaginationChange: setPagination,
  });

  const clearDebounce = () => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }
  };

  useEffect(() => clearDebounce, []);

  const handleSearchChange = (event) => {
    const value = event.target.value;
    setSearchValue(value);
    clearDebounce();
    debounceRef.current = setTimeout(
        () => setGlobalFilter(value), searchDebounceMs);
  };

  // The clear button was never debounced, only typing was.
  const handleSearchReset = () => {
    clearDebounce();
    setSearchValue('');
    setGlobalFilter('');
  };

  const handleExportCsv = () => {
    setMenuOpen(false);
    // Every column, and every filtered-and-sorted row rather than the page on
    // screen -- both are what the old CSV export wrote.
    downloadCsv(
        buildCsv(table.getAllLeafColumns(), table.getSortedRowModel().rows),
        exportFileName);
  };

  const handlePrint = () => {
    setMenuOpen(false);
    setPrinting(true);
  };

  useEffect(() => {
    if (!printing) {
      return undefined;
    }
    const done = () => setPrinting(false);
    window.addEventListener('afterprint', done);
    try {
      window.print();
    } catch {
      // jsdom, and anything else without a print dialog: nothing to wait for.
    }
    done();
    return () => window.removeEventListener('afterprint', done);
  }, [printing]);

  // Menus close on an outside click or on Escape, as the export menu did.
  const closeMenu = useCallback((event) => {
    if (event.type === 'keydown' && event.key !== 'Escape') {
      return;
    }
    if (event.type === 'mousedown' && exportRef.current?.contains(event.target)) {
      return;
    }
    setMenuOpen(false);
  }, []);

  useEffect(() => {
    if (!menuOpen) {
      return undefined;
    }
    document.addEventListener('mousedown', closeMenu);
    document.addEventListener('keydown', closeMenu);
    return () => {
      document.removeEventListener('mousedown', closeMenu);
      document.removeEventListener('keydown', closeMenu);
    };
  }, [menuOpen, closeMenu]);

  const pageRows = table.getRowModel().rows;
  const rowCount = table.getRowCount();
  const from = rowCount === 0
      ? 0
      : activePagination.pageIndex * activePagination.pageSize + 1;
  const to = Math.min(
      rowCount,
      (activePagination.pageIndex + 1) * activePagination.pageSize);

  return (
      <Wrapper className={printing ? 'data-table-print-root' : undefined}>
        {printing && <PrintStyle/>}

        <div className="data-table-toolbar">
          <div className="data-table-export" ref={exportRef}>
            <button
                type="button"
                className="data-table-button"
                aria-haspopup="menu"
                aria-expanded={menuOpen}
                onClick={() => setMenuOpen((open) => !open)}
            >
              <MdSaveAlt size={20}/>
              Export
            </button>
            {menuOpen && (
                <ul className="data-table-menu" role="menu">
                  <li role="none">
                    <button type="button" role="menuitem"
                            onClick={handleExportCsv}>
                      Download as CSV
                    </button>
                  </li>
                  <li role="none">
                    <button type="button" role="menuitem" onClick={handlePrint}>
                      Print
                    </button>
                  </li>
                </ul>
            )}
          </div>

          <div className="data-table-toolbar-spacer"/>

          <div className="data-table-search">
            <MdSearch size={20}/>
            <input
                type="search"
                aria-label="Search"
                placeholder="Search…"
                value={searchValue}
                onChange={handleSearchChange}
            />
            <button
                type="button"
                aria-label="Clear"
                className={`data-table-search-clear${searchValue
                    ? ''
                    : ' is-hidden'}`}
                onClick={handleSearchReset}
            >
              <MdClose size={20}/>
            </button>
          </div>
        </div>

        <div className="data-table-main">
          <table>
            <thead>
            {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id}>
                  {headerGroup.headers.map((header) => {
                    const sorted = header.column.getIsSorted();
                    return (
                        <th
                            key={header.id}
                            scope="col"
                            aria-sort={sorted
                                ? (sorted === 'desc'
                                    ? 'descending'
                                    : 'ascending')
                                : undefined}
                        >
                          {header.isPlaceholder ? null : (
                              header.column.getCanSort() ? (
                                  <button
                                      type="button"
                                      className="data-table-sort"
                                      onClick={header.column.getToggleSortingHandler()}
                                  >
                                    <table.FlexRender header={header}/>
                                    <MdArrowUpward
                                        size={18}
                                        aria-hidden="true"
                                        className={`data-table-sort-icon${sorted
                                            ? ' is-active'
                                            : ''}${sorted === 'desc'
                                            ? ' is-desc'
                                            : ''}`}
                                    />
                                  </button>
                              ) : <table.FlexRender header={header}/>
                          )}
                        </th>
                    );
                  })}
                </tr>
            ))}
            </thead>
            <tbody>
            {pageRows.map((row) => (
                <tr key={row.id}>
                  {row.getAllCells().map((cell) => (
                      <td key={cell.id}>
                        <table.FlexRender cell={cell}/>
                      </td>
                  ))}
                </tr>
            ))}
            </tbody>
          </table>

          {loading && (
              <div className="data-table-overlay">
                <span className="data-table-spinner" role="progressbar"
                      aria-label="Loading"/>
              </div>
          )}
          {!loading && rowCount === 0 && (
              <div className="data-table-overlay">No rows</div>
          )}
        </div>

        <div className="data-table-footer">
          <div className="data-table-page-size">
            <span id="data-table-page-size-label">Rows per page:</span>
            <select
                aria-labelledby="data-table-page-size-label"
                value={pagination.pageSize}
                onChange={(event) => table.setPageSize(
                    Number(event.target.value))}
            >
              {pageSizeOptions.map((option) => (
                  <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </div>
          <span>{from}&ndash;{to} of {rowCount}</span>
          <button
              type="button"
              className="data-table-page-button"
              aria-label="Go to previous page"
              disabled={!table.getCanPreviousPage()}
              onClick={() => table.previousPage()}
          >
            <MdKeyboardArrowLeft size={24}/>
          </button>
          <button
              type="button"
              className="data-table-page-button"
              aria-label="Go to next page"
              disabled={!table.getCanNextPage()}
              onClick={() => table.nextPage()}
          >
            <MdKeyboardArrowRight size={24}/>
          </button>
        </div>
      </Wrapper>
  );
};

export default DataTable;
