import "./App.css";

import {BrowserRouter, Route, Routes} from "react-router-dom";
import 'react-toastify/dist/ReactToastify.css'
import {ToastContainer} from "react-toastify";
import {
    Landing,
    Error,
    ProtectedRoute,
    SharedLayout,
    Register,
    UserSharedLayout,
    Profile,
    Video,
    Stats,
    ChangePassword,
    ForgotPassword,
    UserProtectedRoute

} from "./pages"
import {useSelector} from "react-redux";
import StatsAziz from "./pages/StatsAziz"
import {ChartsContainer} from "./components";

function App() {



    const {user} = useSelector((store) => store.user);
    return (

        <BrowserRouter>

            <Routes>

                {user && user.role === 'ADMIN' && <Route
                    path='/'
                    element={
                        <UserProtectedRoute>
                            <UserSharedLayout/>
                        </UserProtectedRoute>
                    }
                >
                    <Route index element={<ChartsContainer/>}/>
                    <Route path='statistics' element={<ChartsContainer/>}/>
                    <Route path='video' element={<Video/>}/>
                    <Route path='profile' element={<Profile/>}/>


                </Route>}
                <Route path='/' element={<Landing/>}/>
                <Route path='landing' element={<Landing/>}/>
                <Route path='register' element={<Register/>}/>
                <Route path='forgot-password' element={<ForgotPassword/>}/>
                <Route path='change-password' element={<ChangePassword/>}/>
                <Route path='*' element={<Error/>}/>
            </Routes>
            <ToastContainer position='top-center'/>
        </BrowserRouter>
    )
        ;

}

export default App;