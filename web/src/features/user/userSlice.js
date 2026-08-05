import {toast} from "react-toastify";
import {createSlice, createAsyncThunk} from "@reduxjs/toolkit";
import customFetch from "../../util/axios";
import {addUserToLocalStorage, getUserFromLocalStorage, removeUserFromLocalStorage} from "../../util/localStorage";
import {
    clearStoreThunk,
    updateUserThunk,
} from './userThunk';


const initialState = {
    isLoading: false,
    isSidebarOpen: false,
    user: getUserFromLocalStorage(),
};

export const clearStore = createAsyncThunk('user/clearStore', clearStoreThunk);
export const registerUser = createAsyncThunk(
    'user/registerUser',
    async (user, thunkAPI) => {
        try {
            const resp = await customFetch.post('/auth/register ', user);
            return resp.data;
        } catch (error) {
            if (error.response.data.status === 400) {
                toast.error(JSON.stringify(error.response.data.errors))
            }
            if (error.response.status === 409) {
                toast.error(error.response.data.message)
            }
            return thunkAPI.rejectWithValue(error.response.data.msg);
        }
    })

export const loginUser = createAsyncThunk(
    'user/loginUser',
    async (user, thunkAPI) => {
        try {
            const resp = await customFetch.post('/auth/login', user);
            return resp.data;
        } catch (error) {
            if (error.response.status === 401) {
                toast.error(error.response.data.message)
            }
            if (error.response.status === 404) {
                toast.error(error.response.data.message)
            }
            return thunkAPI.rejectWithValue(error.response.data[0].message);
        }
    })
export const forgotPassword = createAsyncThunk(
    'user/forgot-password',
    async (email, thunkAPI) => {

        try {
            const resp = await customFetch.post('/auth/forgot-password ', email);
            toast.success("Password Change Mail Sent...")

            return resp.data;
        } catch (error) {
            if (error.response.status === 403) {

                toast.error("Server Side Problem Occured!!")
            }
            if (error.response.status === 404) {

                toast.error("Email Related Problem Occured!!")
            }
            return thunkAPI.rejectWithValue(error.response.data.msg);
        }
    })

export const changePassword = createAsyncThunk(
    'user/change-password',
    async ({ password, confirmPassword, secretKey }, thunkAPI) => {
        try {
            const resp = await customFetch.post(`/auth/change-password`, {
                password,
                confirmPassword,
                secretKey
            });
            toast.success('Password Changed Successfully...');
            return resp.data;
        } catch (error) {
            console.error(error);
            toast.error('Something Went Wrong!!!');
            return thunkAPI.rejectWithValue(error.response.data.msg);
        }
    }
);



export const updateUser = createAsyncThunk(
    'user/updateUser',
    async (user, thunkAPI) => {
        return updateUserThunk('/auth/update-user', user, thunkAPI);
    }
);


const userSlice = createSlice({
    name: 'user',
    initialState,
    reducers: {
        toggleSidebar: (state) => {
            state.isSidebarOpen = !state.isSidebarOpen;
        },
        logoutUser: (state) => {
            state.user = null;
            state.isSidebarOpen = false;
            removeUserFromLocalStorage();
        },
    },
    // Builder-callback form. The object-map form this used to be was removed in
    // Redux Toolkit 2.x -- it silently matched nothing rather than failing.
    extraReducers: (builder) => {
        builder
            .addCase(registerUser.pending, (state) => {
                state.isLoading = true;
            })
            .addCase(registerUser.fulfilled, (state, {payload}) => {
                const {user} = payload;
                state.isLoading = false;
                state.user = user;
                addUserToLocalStorage(user);
                toast.success(`Hello There ${user.name}`);
            })
            .addCase(registerUser.rejected, (state, {payload}) => {
                state.isLoading = false;
                toast.error(payload);
            })
            .addCase(loginUser.pending, (state) => {
                state.isLoading = true;
            })
            .addCase(loginUser.fulfilled, (state, {payload}) => {
                const {user} = payload;
                state.isLoading = false;
                state.user = user;
                addUserToLocalStorage(user);
                toast.success(`Hello There ${user.name}`);
            })
            .addCase(loginUser.rejected, (state, {payload}) => {
                state.isLoading = false;
                toast.error(payload);
            })
            .addCase(updateUser.pending, (state) => {
                state.isLoading = true;
            })
            .addCase(updateUser.fulfilled, (state, {payload}) => {
                const {user} = payload;
                state.isLoading = false;
                state.user = user;

                addUserToLocalStorage(user);
                toast.success('Password Changed Successfully!');
            })
            .addCase(updateUser.rejected, (state, {payload}) => {
                state.isLoading = false;
                toast.error(payload);
            });
    }

});
export const {toggleSidebar, logoutUser} = userSlice.actions;
export default userSlice.reducer;


