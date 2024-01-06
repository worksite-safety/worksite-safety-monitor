import "./App.css";

import {BrowserRouter, Route, Routes} from "react-router-dom";
import 'react-toastify/dist/ReactToastify.css'
import {ToastContainer} from "react-toastify";
import {
    Landing,
    Error, ProtectedRoute, SharedLayout, Register, UserSharedLayout, Profile, Stats
} from "./pages"
import {useSelector} from "react-redux";
import StatsAziz from "./pages/StatsAziz"
import {ChartsContainer} from "./components";

function App() {


  const { user} = useSelector((store) => store.user);
  return (

      <BrowserRouter>

        <Routes>

          {user && user.role === 'USER' && <Route
              path='/'
              element={
                <ProtectedRoute>
                  <UserSharedLayout/>
                </ProtectedRoute>
              }
          >
              <Route index element={<Stats/>}/>
              <Route path='statistics' element={<ChartsContainer/>}/>
              <Route path='profile' element={<Profile/>}/>



          </Route>}
          <Route path='/' element={<Landing/>}/>
          <Route path='landing' element={<Landing/>}/>
          <Route path='register' element={<Register/>}/>

          <Route path='*' element={<Error/>}/>
          {user && user.role === 'ADMIN' && <Route
              path='/'
              element={
                <ProtectedRoute>
                  <SharedLayout/>
                </ProtectedRoute>
              }
          >
            <Route index element={<Profile/>}/>
          </Route>}
        </Routes>
        <ToastContainer position='top-center'/>
      </BrowserRouter>
  )
      ;
}

export default App;