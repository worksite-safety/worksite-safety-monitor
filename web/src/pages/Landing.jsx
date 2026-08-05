import React from 'react';
import main from '../assets/images/firstLogo.svg'
import Wrapper from '../assets/wrappers/LandingPage'
import {Logo} from "../components";
import {Link} from "react-router-dom";


const Landing = () => {
    return (
        <Wrapper>
            <nav>
                <Logo/>
            </nav>
            <div className='container page'>
                <div className='info'>
                    <h1>
                        Worksite <span>AI</span> Guardian
                    </h1>
                    <p>Protecting Lives, One Frame at a Time: AI Insights for Safer Work Environments.</p>
                    <Link to={"/register"} className='btn'>Login/Register</Link>
                </div>
                <img src={main} alt='ai project hunt' className='img main-img'/>
            </div>
        </Wrapper>
    );
};


export default Landing;