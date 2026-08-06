import React, { useEffect, useState } from "react";
import Wrapper from "../assets/wrappers/ProfilePage";
import { useDispatch, useSelector } from "react-redux";
import { toast } from "react-toastify";
import { updateUser } from "../features/user/userSlice";
import "./profile.css";
// Were @mui/icons-material's BadgeOutlined and EmailOutlined; MdOutlineBadge
// and MdOutlineEmail are the same Material glyphs (identical path data, 24x24
// viewBox). react-icons sizes to 1em, and these sit inside the ProfilePage
// wrapper's h3 (35px) and h4 (25px), so unsized they would render 46% and 4%
// larger than MUI's fixed 1.5rem. ICON_SIZE restores the drawn size.
import { MdOutlineBadge, MdOutlineEmail } from "react-icons/md";

// MUI SvgIcon's default fontSize="medium" resolved to 1.5rem (24px at the
// app's 100% root font size). Keep it in rem so it still tracks a user's
// browser font-size preference the way the MUI icon did.
const ICON_SIZE = "1.5rem";

const Profile = () => {
  const { isLoading, user } = useSelector((store) => store.user);
  const dispatch = useDispatch();

  const [userUpdateData, setUserUpdateDataData] = useState({
    newPassword: "",
    newPasswordConfirm: "",
    token:user.token || "",
  });
  const [userData, setUserData] = useState({
    id: user?.id || "",
    lastName: user?.lastName || "",
    name: user?.name || "",
    role: user?.role || "",

    email: user?.email || "",
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    const { newPassword, newPasswordConfirm } = userUpdateData;

    if (!newPassword || !newPasswordConfirm) {
      toast.error("Please Fill Out All Fields");
      return;
    }
    if (newPassword !== newPasswordConfirm) {
      toast.error("Passwords Do Not Match");
      return;
    }
    dispatch(updateUser(userUpdateData));

  };
  const handleChange = (e) => {
    const name = e.target.name;
    const value = e.target.value;

    setUserUpdateDataData((prevState) => ({ ...prevState, [name]: value }));
  };

  useEffect(() => {});

  return (
      <Wrapper className="profile-wrapper">
        <div className="user-info">
          <h2>User Information</h2>
          <div className="user-details">
            <h3 >
              <MdOutlineBadge style={{fontSize: ICON_SIZE}} aria-hidden="true" focusable="false"/> {userData.name} {userData.lastName}
            </h3>
            <h4  style={{textTransform: 'none'}} className="user-email">
              <MdOutlineEmail style={{fontSize: ICON_SIZE}} aria-hidden="true" focusable="false"/> {userData.email}
            </h4>
          </div>
        </div>

        <form className="user-profile-form" onSubmit={handleSubmit}>
          <div className="form-container">
            <div className="change-password-section">
              <h2>Change Password</h2>
              <div className="password-fields">
                <div className="input-w-label">
                  <label>New Password:</label>
                  <input
                      type="password"
                      name="newPassword"
                      value={userUpdateData.newPassword}
                      onChange={handleChange}
                      className="password-input"
                  />
                </div>
                <div className="input-w-label">
                  <label>Confirm Password:</label>
                  <input
                      type="password"
                      name="newPasswordConfirm"
                      value={userUpdateData.newPasswordConfirm}
                      onChange={handleChange}
                      className="password-input"
                  />
                </div>

                <button className="submit-btn" type="submit" disabled={isLoading}>
                  {isLoading ? "Please Wait..." : "Update Information"}
                </button>
              </div>
            </div>
          </div>
        </form>
      </Wrapper>
  );
};

export default Profile;
