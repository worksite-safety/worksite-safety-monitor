import axios from "axios";
import {clearStore} from "../features/user/userSlice";
import {removeUserFromLocalStorage} from "./localStorage";
import {toast} from "react-toastify";

const customFetch = axios.create({
    baseURL: 'http://localhost:8080/'
})

export const checkForUnauthorizedResponse = (error, thunkAPI) => {
    if (error.response.status === 403) {
        thunkAPI.dispatch(clearStore());
        return thunkAPI.rejectWithValue('Unauthorized! Logging Out...');
    }
    return thunkAPI.rejectWithValue(error.response.data.msg);
};

customFetch.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error.response.status === 403) {
            removeUserFromLocalStorage();
            window.location.assign("/landing");
        }
        return Promise.reject(error);
    }
);

export default customFetch;