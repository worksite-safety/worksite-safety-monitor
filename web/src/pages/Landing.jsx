import React from 'react';
import main from '../assets/images/firstLogo.svg'
import Wrapper from '../assets/wrappers/LandingPage'
import {Logo, SafetyNotice} from "../components";
import {Link} from "react-router";


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
                    {/* The old tagline was "Protecting Lives, One Frame at a Time".
                        Nothing measured supports it: fall detection scores
                        mAP@0.5 = 0.589, and neither gesture detector has ever
                        fired on real footage. This one claims only what the
                        system demonstrably does. */}
                    <p>Counts falls and missing PPE from a single camera feed, and charts what it
                        found, day by day.</p>
                    <SafetyNotice/>
                    <Link to={"/register"} className='btn'>Login/Register</Link>
                </div>
                <img src={main} alt='ai project hunt' className='img main-img'/>
            </div>
        </Wrapper>
    );
};


export default Landing;
