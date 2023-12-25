import axios from "axios";
import {clearStore} from "../features/user/userSlice";

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

export default customFetch;