import styled from 'styled-components'

// One quiet line, on every route. --footer-height in index.css is what the
// full-height pages subtract so this does not land below the fold; keep the two
// in step if the padding here changes.
const Wrapper = styled.footer`
  width: var(--fluid-width);
  max-width: var(--max-width);
  margin: 0 auto;
  padding: 0.75rem 0;
  border-top: 1px solid var(--grey-100);
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.25rem 0.75rem;
  font-size: var(--small-text);
  line-height: 1.4;
  color: var(--grey-500);

  .sep {
    color: var(--grey-300);
  }

  a {
    color: var(--primary-500);
    text-decoration: none;
    border-bottom: 1px solid transparent;
    transition: var(--transition);
  }
  a:hover,
  a:focus-visible {
    border-bottom-color: var(--primary-500);
  }
`
export default Wrapper
