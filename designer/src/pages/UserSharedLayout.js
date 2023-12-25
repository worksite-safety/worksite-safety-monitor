import { Outlet } from 'react-router-dom';
import Wrapper from '../assets/wrappers/SharedLayout';
import {UserBigSidebar, UserSmallSidebar} from "../components";
import Navbar from "../components/Navbar";

const UserSharedLayout = () => {
    return (
        <Wrapper>
            <main className='dashboard'>

                <UserSmallSidebar />
                <UserBigSidebar />
                <div>
                    <Navbar />
                    <div className='dashboard-page'>
                        <Outlet />
                    </div>
                </div>
            </main>
        </Wrapper>
    );
};
export default UserSharedLayout;