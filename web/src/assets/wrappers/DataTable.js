import styled, {keyframes} from 'styled-components'

/* The reporting grid used to be MUI's DataGrid, which drew all of this for us.
   The measurements here are not invented: they are the ones the DataGrid used
   at the density this page ran at -- 56px header row, 52px body rows, 10px of
   horizontal cell padding, 52px footer -- so the page keeps the shape and the
   row count per screen it had before. Colours come from the app's own
   variables rather than the MUI palette, which is the one deliberate visual
   change. */

const spin = keyframes`
  to {
    transform: rotate(360deg);
  }
`

const Wrapper = styled.div`
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--white);
  color: var(--textColor);
  border: 1px solid var(--grey-100);
  border-radius: var(--borderRadius);
  font-family: var(--bodyFont);
  font-size: 0.875rem;
  line-height: 1.43;

  /* ----- toolbar ----- */
  .data-table-toolbar {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    min-height: 3rem;
    padding: 0.25rem 0.5rem;
    border-bottom: 1px solid var(--grey-100);
  }
  .data-table-toolbar-spacer {
    flex: 1;
  }
  .data-table-button {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.25rem 0.5rem;
    background: transparent;
    border: transparent;
    border-radius: var(--borderRadius);
    color: var(--primary-500);
    font-family: inherit;
    font-size: 0.8125rem;
    font-weight: 500;
    letter-spacing: var(--letterSpacing);
    text-transform: uppercase;
    cursor: pointer;
    transition: var(--transition);
  }
  .data-table-button:hover {
    background: var(--grey-50);
  }

  /* ----- export menu ----- */
  .data-table-export {
    position: relative;
  }
  .data-table-menu {
    position: absolute;
    top: calc(100% + 0.25rem);
    left: 0;
    z-index: 5;
    min-width: 11rem;
    margin: 0;
    padding: 0.25rem 0;
    list-style-type: none;
    background: var(--white);
    border-radius: var(--borderRadius);
    box-shadow: var(--shadow-3);
  }
  .data-table-menu button {
    display: block;
    width: 100%;
    padding: 0.375rem 1rem;
    background: transparent;
    border: none;
    color: var(--textColor);
    font-family: inherit;
    font-size: 0.875rem;
    text-align: left;
    cursor: pointer;
  }
  .data-table-menu button:hover {
    background: var(--grey-50);
  }

  /* ----- quick filter ----- */
  .data-table-search {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.125rem 0.25rem;
    color: var(--grey-500);
    border-bottom: 1px solid var(--grey-200);
    transition: var(--transition);
  }
  .data-table-search:focus-within {
    border-bottom-color: var(--primary-500);
  }
  .data-table-search input {
    width: 12rem;
    max-width: 40vw;
    padding: 0.25rem;
    background: transparent;
    border: none;
    outline: none;
    color: var(--textColor);
    font-family: inherit;
    font-size: 0.875rem;
  }
  /* the browsers' own search affordances duplicate the clear button */
  .data-table-search input::-webkit-search-cancel-button,
  .data-table-search input::-webkit-search-decoration {
    display: none;
  }
  .data-table-search-clear {
    display: inline-flex;
    padding: 0.125rem;
    background: transparent;
    border: none;
    border-radius: 50%;
    color: inherit;
    cursor: pointer;
  }
  .data-table-search-clear:hover {
    background: var(--grey-50);
  }
  .data-table-search-clear.is-hidden {
    visibility: hidden;
  }

  /* ----- the grid itself ----- */
  .data-table-main {
    position: relative;
    flex: 1;
    overflow: auto;
  }
  table {
    width: 100%;
    table-layout: fixed;
    border-collapse: collapse;
  }
  thead th {
    position: sticky;
    top: 0;
    z-index: 1;
    height: 56px;
    padding: 0 10px;
    background: var(--white);
    border-bottom: 1px solid var(--grey-100);
    color: var(--grey-800);
    font-weight: 500;
    text-align: left;
    white-space: nowrap;
  }
  tbody td {
    height: 52px;
    padding: 0 10px;
    border-bottom: 1px solid var(--grey-100);
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
  tbody tr:hover {
    background: var(--grey-50);
  }

  .data-table-sort {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0;
    background: transparent;
    border: none;
    color: inherit;
    font: inherit;
    cursor: pointer;
  }
  .data-table-sort-icon {
    opacity: 0;
    transition: var(--transition);
  }
  .data-table-sort:hover .data-table-sort-icon,
  .data-table-sort:focus-visible .data-table-sort-icon {
    opacity: 0.5;
  }
  .data-table-sort-icon.is-active {
    opacity: 1;
  }
  .data-table-sort-icon.is-desc {
    transform: rotate(180deg);
  }

  .data-table-delete {
    cursor: pointer;
  }

  /* ----- overlays ----- */
  .data-table-overlay {
    position: absolute;
    top: 56px;
    right: 0;
    bottom: 0;
    left: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(255, 255, 255, 0.38);
  }
  .data-table-spinner {
    width: 40px;
    height: 40px;
    border: 4px solid var(--grey-100);
    border-top-color: var(--primary-500);
    border-radius: 50%;
    animation: ${spin} 1s linear infinite;
  }

  /* ----- footer ----- */
  .data-table-footer {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 0.75rem;
    min-height: 52px;
    padding: 0 0.5rem;
    border-top: 1px solid var(--grey-100);
    color: var(--grey-700);
  }
  .data-table-page-size {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  .data-table-page-size select {
    padding: 0.125rem 0.25rem;
    background: transparent;
    border: none;
    color: inherit;
    font-family: inherit;
    font-size: 0.875rem;
    cursor: pointer;
  }
  .data-table-page-button {
    display: inline-flex;
    padding: 0.375rem;
    background: transparent;
    border: none;
    border-radius: 50%;
    color: inherit;
    cursor: pointer;
  }
  .data-table-page-button:hover:not(:disabled) {
    background: var(--grey-50);
  }
  .data-table-page-button:disabled {
    color: var(--grey-300);
    cursor: not-allowed;
  }
`

export default Wrapper
