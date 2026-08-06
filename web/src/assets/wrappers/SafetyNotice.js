import styled from 'styled-components'

const Wrapper = styled.aside`
  max-width: 40em;
  margin-bottom: 1.5rem;
  padding: 1rem 1.25rem;
  background: var(--white);
  border-left: 4px solid var(--primary-600);
  border-radius: var(--borderRadius);
  box-shadow: var(--shadow-1);

  h2 {
    /* index.css capitalises every heading; this one is a sentence. */
    text-transform: none;
    font-size: 1.25rem;
    margin-bottom: 0.5rem;
    color: var(--grey-900);
  }

  p {
    margin-bottom: 0;
    font-size: var(--small-text);
    line-height: 1.6;
    color: var(--grey-700);
  }

  a {
    color: var(--primary-500);
  }
`
export default Wrapper
