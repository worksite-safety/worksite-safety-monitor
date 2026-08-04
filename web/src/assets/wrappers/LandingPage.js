import styled from 'styled-components'

const Wrapper = styled.main`
  nav {
    width: var(--fluid-width);
    max-width: var(--max-width);
    margin: 0 auto;
    height: var(--nav-height);
    display: flex;
    align-items: center;
  }
  .page {
    min-height: calc(100vh - var(--nav-height));
    display: grid;
    align-items: center;
    margin-top: -3rem;
  }
  h1 {
    font-weight: 700;
    span {
      color: var(--primary-500);
    }
  }
  p {
    color: var(--grey-600);
  }
  .main-img {
    display: none;
  }
  @media (min-width: 992px) {
    .page {
      grid-template-columns: 1fr 1fr;
      column-gap: 3rem;
    }
    .main-img {
      display: block;
    }
  }

  .member-btn {
    background: transparent;
    border: transparent;
    color: var(--primary-500);
    cursor: pointer;
    letter-spacing: var(--letterSpacing);
  }
  .title{
    margin-right: 463px;
    font-family: "Source Sans Pro",sans-serif;
    line-height:1.5;
    display: block;
    font-size: var(--smallText);
    text-transform: capitalize;
    font-weight:400;
    
    
  }

  .leaflet-container {
    height: 200px;
    width: 90%;
    border-radius: 2rem;
}

.cluster-icon {
    background-color: #333;
    height: 2em;
    width: 2em;
    color: #fff;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    font-size: 1.2rem;
    box-shadow: 0 0 0px 5px #fff;
}
.container-konum {
    margin-top: 600px;
    position: fixed;
    width: 90%;
    height: 200px;
    border-radius: 50px;
    text-align: center;
    font-size: 30px;
    box-shadow: 2px 2px 3px #999;
    z-index: 100;
}

`;
export default Wrapper
