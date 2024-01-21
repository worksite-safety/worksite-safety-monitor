import os
import cv2
import numpy as np
import math
import datetime
import argparse
import time
from ultralytics import YOLO
from ultralytics.yolo.utils.plotting import Annotator, Colors
from copy import deepcopy
from datetime import datetime, timedelta
from kafka import KafkaProducer
import json


producer = KafkaProducer(bootstrap_servers='localhost:9092')



sport_list = {
    'armsUp': {
        'left_points_idx': [11, 5, 7],
        'right_points_idx': [12, 6, 8],
        'maintaining': 30,
        'relaxing': 140,
        'concerned_key_points_idx': [5, 6, 7, 8, 11, 12],
        'concerned_skeletons_idx': [[12, 6], [6, 8], [11, 5], [5, 7]]
    },
    'bending': {
        'left_points_idx': [5, 11, 13],
        'right_points_idx': [6, 12, 14],
        'maintaining': 130,
        'relaxing': 160,
        'concerned_key_points_idx': [5, 6, 11, 12, 13, 14],
        'concerned_skeletons_idx': [[14, 12], [12, 6], [13, 11], [11, 5]]
    },
    'frontbending': {
        'left_points_idx': [3, 11, 13],
        'right_points_idx': [4, 12, 14],
        'maintaining': 130,
        'relaxing': 160,
        'concerned_key_points_idx': [3, 4, 11, 12, 13, 14],
        'concerned_skeletons_idx': [[14, 12], [12, 4], [13, 11], [11, 3]]
    }
}


def calculate_angle(key_points, left_points_idx, right_points_idx):
    def _calculate_angle(line1, line2):
        # Calculate the slope of two straight lines
        slope1 = math.atan2(line1[3] - line1[1], line1[2] - line1[0])
        slope2 = math.atan2(line2[3] - line2[1], line2[2] - line2[0])

        # Convert radians to angles
        angle1 = math.degrees(slope1)
        angle2 = math.degrees(slope2)

        # Calculate angle difference
        angle_diff = abs(angle1 - angle2)

        # Ensure the angle is between 0 and 180 degrees
        if angle_diff > 180:
            angle_diff = 360 - angle_diff

        return angle_diff

    left_points = [[key_points.data[0][i][0], key_points.data[0][i][1]] for i in left_points_idx]
    right_points = [[key_points.data[0][i][0], key_points.data[0][i][1]] for i in right_points_idx]
    line1_left = [
        left_points[1][0].item(), left_points[1][1].item(),
        left_points[0][0].item(), left_points[0][1].item()
    ]
    line2_left = [
        left_points[1][0].item(), left_points[1][1].item(),
        left_points[2][0].item(), left_points[2][1].item()
    ]
    angle_left = _calculate_angle(line1_left, line2_left)
    line1_right = [
        right_points[1][0].item(), right_points[1][1].item(),
        right_points[0][0].item(), right_points[0][1].item()
    ]
    line2_right = [
        right_points[1][0].item(), right_points[1][1].item(),
        right_points[2][0].item(), right_points[2][1].item()
    ]
    angle_right = _calculate_angle(line1_right, line2_right)
    angle = (angle_left + angle_right) / 2
    return angle


def plot(pose_result, plot_size_redio, show_points=None, show_skeleton=None):
    class _Annotator(Annotator):

        def kpts(self, kpts, shape=(640, 640), radius=5, line_thickness=2, kpt_line=True):
            if self.pil:
                # Convert to numpy first
                self.im = np.asarray(self.im).copy()
            nkpt, ndim = kpts.shape
            is_pose = nkpt == 17 and ndim == 3
            kpt_line &= is_pose  # `kpt_line=True` for now only supports human pose plotting
            colors = Colors()
            for i, k in enumerate(kpts):
                if show_points is not None:
                    if i not in show_points:
                        continue
                color_k = [int(x) for x in self.kpt_color[i]] if is_pose else colors(i)
                x_coord, y_coord = k[0], k[1]
                if x_coord % shape[1] != 0 and y_coord % shape[0] != 0:
                    if len(k) == 3:
                        conf = k[2]
                        if conf < 0.5:
                            continue
                    cv2.circle(self.im, (int(x_coord), int(y_coord)),
                               int(radius * plot_size_redio), color_k, -1, lineType=cv2.LINE_AA)

            if kpt_line:
                ndim = kpts.shape[-1]
                for i, sk in enumerate(self.skeleton):
                    if show_skeleton is not None:
                        if sk not in show_skeleton:
                            continue
                    pos1 = (int(kpts[(sk[0] - 1), 0]), int(kpts[(sk[0] - 1), 1]))
                    pos2 = (int(kpts[(sk[1] - 1), 0]), int(kpts[(sk[1] - 1), 1]))
                    if ndim == 3:
                        conf1 = kpts[(sk[0] - 1), 2]
                        conf2 = kpts[(sk[1] - 1), 2]
                        if conf1 < 0.5 or conf2 < 0.5:
                            continue
                    if pos1[0] % shape[1] == 0 or pos1[1] % shape[0] == 0 or pos1[0] < 0 or pos1[1] < 0:
                        continue
                    if pos2[0] % shape[1] == 0 or pos2[1] % shape[0] == 0 or pos2[0] < 0 or pos2[1] < 0:
                        continue
                    cv2.line(self.im, pos1, pos2, [int(x) for x in self.limb_color[i]],
                             thickness=int(line_thickness * plot_size_redio), lineType=cv2.LINE_AA)
            if self.pil:
                # Convert im back to PIL and update draw
                self.fromarray(self.im)

    annotator = _Annotator(deepcopy(pose_result.orig_img))
    if pose_result.keypoints is not None:
        for k in reversed(pose_result.keypoints.data):
            annotator.kpts(k, pose_result.orig_shape, kpt_line=True)
    return annotator.result()


def put_text(frame, exercise1, count1, exercise2, count2, fps, redio):
    cv2.rectangle(
        frame, (int(20 * redio), int(20 * redio)), (frame.shape[1], int(163 * redio*2/3)),
        (255, 104, 104), -1
    )

    if exercise1 in sport_list.keys():
        cv2.putText(
            frame, f'Exercise 1: {exercise1}', (int(30 * redio), int(50 * redio)), 0, 0.9 * redio,
            (255, 255, 255), thickness=int(2 * redio), lineType=cv2.LINE_AA
        )
    elif exercise1 == 'No Object':
        cv2.putText(
            frame, f'No Object', (int(30 * redio), int(50 * redio)), 0, 0.9 * redio,
            (255, 255, 255), thickness=int(2 * redio), lineType=cv2.LINE_AA
        )

    if exercise2 in sport_list.keys():
        cv2.putText(
            frame, f'Exercise 2: {exercise2}', (int((frame.shape[1] - 250) * redio), int(50 * redio)), 0, 0.9 * redio,
            (255, 255, 255), thickness=int(2 * redio), lineType=cv2.LINE_AA
        )
    elif exercise2 == 'No Object':
        cv2.putText(
            frame, f'No Object', (int((frame.shape[1] - 250) * redio), int(50 * redio)), 0, 0.9 * redio,
            (255, 255, 255), thickness=int(2 * redio), lineType=cv2.LINE_AA
        )

    cv2.putText(
        frame, f'Count 1: {count1}', (int(30 * redio), int(100 * redio)), 0, 0.9 * redio,
        (255, 255, 255), thickness=int(2 * redio), lineType=cv2.LINE_AA
    )

    cv2.putText(
        frame, f'Count 2: {count2}', (int((frame.shape[1] - 250) * redio), int(100 * redio)), 0, 0.9 * redio,
        (255, 255, 255), thickness=int(2 * redio), lineType=cv2.LINE_AA
    )




def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default='yolov8s-pose.pt', type=str, help='path to model weight')
    parser.add_argument('--sport', default='squat', type=str,
                        help='Currently supported "sit-up", "pushup" and "squat"')
    parser.add_argument('--input', default="0", type=str, help='path to input video')
    parser.add_argument('--save_dir', default=None, type=str, help='path to save output')
    parser.add_argument('--show', default=True, type=bool, help='show the result')
    args = parser.parse_args()
    return args

class Args:
    def __init__(self):
        # Set default values
        self.model = 'yolov8s-pose.pt'
        self.sport2 = 'armsUp'
        self.input = "0"
        self.save_dir = None
        self.show = True

class Args2:
    def __init__(self):
        # Set default values
        self.model = 'yolov8s-pose.pt'
        self.sport = 'bending'
        self.input = "0"
        self.save_dir = None
        self.show = True



def main():
    from ultralytics import YOLO
    model2 = YOLO("best.pt")

    bulk_insert_interval = 60  # 1 minute
    data_batch = []


    # Obtain relevant parameters
    args = Args2()

    # Create an instance of Args
    args2 = Args()

    # Load the YOLOv8 model
    model = YOLO(args.model)

    # Open the video file or camera
    if args.input.isnumeric():
        cap = cv2.VideoCapture(int(args.input))
    else:
        cap = cv2.VideoCapture(args.input)

    # For save result video
    if args.save_dir is not None:
        save_dir = os.path.join(
            args.save_dir, args.sport,
            datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S'))
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        fps = cap.get(cv2.CAP_PROP_FPS)
        size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        output = cv2.VideoWriter(os.path.join(save_dir, 'result.mp4'), fourcc, fps, size)

    # Set variables to record motion status
    angle = [0]*10
    angle2 = [0]*10
    angle3 = [0]*10
    reaching = [False]*10
    reaching_last = [False]*10
    state_keep = [False]*10
    counter = 0
    reaching2 = [0]*10
    reaching_last2 = [0]*10
    state_keep2 = [0]*10
    counter2 = 0
    x1, y1, x2, y2 = 0, 0, 0, 0
    name=""
    controlHelmet = False
    controlJacket = False
    sumHelmet = 0;
    numHelmet = 0;
    sumJacket = 0;
    numJacket = 0;
    current_time_helmet = time.time()
    current_time_jacket = time.time()
    last_insert_time_helmet = 0
    last_insert_time_jacket = 0
    checkLastSendJacket = False
    checkLastSendHelmet = False
    reference_time = datetime.now() - timedelta(minutes=3)
    # Loop through the video frames
    while cap.isOpened():

        # Read a frame from the video
        success, frame = cap.read()

        if success:
            # Set plot size redio for inputs with different resolutions
            plot_size_redio = max(frame.shape[1] / 960, frame.shape[0] / 540)

            # Run YOLOv8 inference on the frame
            results = model(frame,conf = 0.8)

            results2 = model2.predict(frame,show=False,conf=0.6)

            boxes = results2[0].boxes.xyxy.tolist()
            classes = results2[0].boxes.cls.tolist()
            names = results2[0].names
            confidences = results2[0].boxes.conf.tolist()


            if results[0].keypoints.shape[1] == 0:
                if args.show:
                    put_text(frame, args.sport, counter,args2.sport2, counter2, 10, plot_size_redio)
                    scale = 640 / max(frame.shape[0], frame.shape[1])
                    show_frame = cv2.resize(frame, (0, 0), fx=scale, fy=scale)
                if args.save_dir is not None:
                    output.write(frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
                continue

            confidence_scores = []
            for node in results:
                checkNodeVisibility = node.keypoints.conf.tolist()
                numberOfPerson = len(checkNodeVisibility[0])
                data = results[0].keypoints.data
                personIndex = 0
                left = [12, 14, 16]
                right = [11, 13, 15]
                for row in checkNodeVisibility:
                    if row[5] > 0.6 and row[11] > 0.6 and row[13] > 0.6 or row[12] > 0.6 and row[6] > 0.6 and row[14] > 0.6:
                        if calculate_angle(results[0].keypoints[personIndex], left, right) > 160:
                            # Get hyperparameters
                            left_points_idx = sport_list[args.sport]['left_points_idx']
                            right_points_idx = sport_list[args.sport]['right_points_idx']
                            # Calculate angle
                            angle[personIndex] = calculate_angle(results[0].keypoints[personIndex], left_points_idx, right_points_idx)
                            # Determine whether to complete once
                            if angle[personIndex] < sport_list[args.sport]['maintaining']:
                                reaching[personIndex] = True
                            if angle[personIndex] > sport_list[args.sport]['relaxing']:
                                reaching[personIndex] = False
                            if reaching[personIndex] != reaching_last[personIndex]:
                                reaching_last[personIndex] = reaching[personIndex]
                                if reaching[personIndex]:
                                    state_keep[personIndex] = True
                                if not reaching[personIndex] and state_keep[personIndex]:
                                    counter += 1
                                    state_keep[personIndex] = False
                                    prediction_data = {
                                            "startTime": int(time.time() * 1000),
                                            "eventType": 'FRONT_BEND',
                                            "confidencePercentage":row[11],
                                            "cameraName":args.input
                                            }
                                    data_batch.append(prediction_data)

                                    message = json.dumps(prediction_data).encode('utf-8')

                                    key = str(time.time()).encode('utf-8')
                                    producer.send('rawEvents', key=key,value= message)
                                    producer.flush()#Send Message


                                    # Reset variables for the next interval
                                    data_batch = []

                    if row[11] > 0.6 and row[5] > 0.6 and row[7] > 0.6 or row[12] > 0.6 and row[6] > 0.6 and row[8] > 0.6:
                        # Get hyperparameters
                        left_points_idx2 = sport_list[args2.sport2]['left_points_idx']
                        right_points_idx2 = sport_list[args2.sport2]['right_points_idx']
                         # Second
                        # Calculate angle
                        angle2[personIndex] = calculate_angle(results[0].keypoints[personIndex], left_points_idx2, right_points_idx2)

                        # Determine whether to complete once
                        if angle2[personIndex] < sport_list[args2.sport2]['maintaining']:
                            reaching2[personIndex] = True
                        if angle2[personIndex] > sport_list[args2.sport2]['relaxing']:
                            reaching2[personIndex] = False

                        if reaching2[personIndex] != reaching_last2[personIndex]:
                            reaching_last2[personIndex] = reaching2[personIndex]
                            if reaching2[personIndex]:
                                state_keep2[personIndex] = True
                            if not reaching2[personIndex] and state_keep2[personIndex]:
                                counter2 += 1
                                state_keep2[personIndex] = False
                                prediction_data = {
                                            "startTime": int(time.time() * 1000),
                                            "eventType": 'ARMS_UP',
                                            "confidencePercentage":row[7],
                                            "cameraName":args.input
                                            }
                                data_batch.append(prediction_data)


                                message = json.dumps(prediction_data).encode('utf-8')
                                key = str(time.time()).encode('utf-8')

                                producer.send('rawEvents', key=key,value= message)
                                producer.flush()#Send Message

                                # Reset variables for the next interval
                                data_batch = []
                    personIndex = personIndex+1
                    if personIndex > numberOfPerson-1:
                        personIndex = 0

            # Visualize the results on the frame
            annotated_frame = plot(
                results[0], plot_size_redio,
                # sport_list[args.sport]['concerned_key_points_idx'],
                # sport_list[args.sport]['concerned_skeletons_idx']
            )
            # annotated_frame = results[0].plot(boxes=False)

            controlHelmet = True
            controlJacket = False
            # Iterate through the results
            for box, cls, conf in zip(boxes, classes, confidences):
                x1, y1, x2, y2 = box
                confidence = conf
                detected_class = cls
                name = names[int(cls)]
                if name == 'no-helmet':
                    checkLastSendHelmet = True
                    controlHelmet = False
                    sumHelmet = sumHelmet + conf
                    numHelmet = numHelmet + 1
                    if last_insert_time_helmet == 0:
                        last_insert_time_helmet = time.time()
                    current_time_helmet = time.time()  # Capture current time for potential use


                if name == 'no-jacket':
                    checkLastSendJacket = True
                    controlJacket = False
                    sumJacket = sumJacket + conf
                    numJacket = numJacket + 1
                    if last_insert_time_jacket == 0:
                        last_insert_time_jacket = time.time()

                if name == 'fall':
                    current_datetime = datetime.now()
                    if current_datetime > reference_time:
                        reference_time = current_datetime + timedelta(minutes=3)
                        prediction_data = {
                            "startTime": int(time.time() * 1000),
                            "eventType": 'FALL',
                            "confidencePercentage":conf,
                            "cameraName":args.input,
                            "isProcessed":"false"
                        }

                        data_batch.append(prediction_data)
                        message = json.dumps(prediction_data).encode('utf-8')

                        key = str(time.time()).encode('utf-8')
                        producer.send('rawEvents', key=key,value= message)
                        producer.flush()#Send Message

                        # Reset variables for the next interval
                        data_batch = []
                x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(annotated_frame, name, (x1, y1),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (255,255,255), 2, cv2.LINE_AA)


            if checkLastSendHelmet and controlHelmet and numberOfPerson > 0 :
                current_time_helmet = time.time()
                elapsed_time_since_last_insert = current_time_helmet - last_insert_time_helmet
                start_time = last_insert_time_helmet
                end_time = current_time_helmet
                prediction_data = {
                    "timePeriod": int(elapsed_time_since_last_insert),
                    "startTime":int(start_time*1000),
                    "eventType": 'NO_HELMET',
                    "confidencePercentage":sumHelmet/numHelmet,
                    "cameraName":args.input,
                    "isProcessed":"false"
                }

                data_batch.append(prediction_data)
                last_insert_time_helmet = 0


                message = json.dumps(prediction_data).encode('utf-8')
                key = str(time.time()).encode('utf-8')
                producer.send('rawEvents', key=key,value= message)
                producer.flush()#Send Message


                # Reset variables for the next interval
                data_batch = []
                checkLastSendHelmet = False

            if checkLastSendJacket and controlJacket and numberOfPerson > 0 :
                current_time_jacket = time.time()
                elapsed_time_since_last_insert = current_time_jacket - last_insert_time_jacket
                prediction_data = {
                    "timePeriod": int(elapsed_time_since_last_insert),
                    "startTime":int(last_insert_time_jacket*1000),
                    "eventType": 'NO_JACKET',
                    "confidencePercentage":sumJacket/numJacket,
                    "cameraName":args.input,
                    "isProcessed":"false"
                }

                data_batch.append(prediction_data)
                last_insert_time_jacket = 0

                message = json.dumps(prediction_data).encode('utf-8')
                key = str(time.time()).encode('utf-8')


                producer.send('rawEvents', key=key,value= message)
                producer.flush()

                data_batch = []
                checkLastSendJacket = False

            put_text(
                annotated_frame, args.sport, counter,args2.sport2, counter2, 10, plot_size_redio)

            # Display the annotated frame
            if args.show:
                scale = 640 / max(annotated_frame.shape[0], annotated_frame.shape[1])
                show_frame = cv2.resize(annotated_frame, (0, 0), fx=scale, fy=scale)

                # Encode the frame to base64
                output_path = 'output_image.jpg'

                cv2.imwrite(output_path, show_frame)
                #cv2.imshow("Output", show_frame)
            if args.save_dir is not None:
                output.write(annotated_frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
        else:
            # Break the loop if the end of the video is reached
            break

    # Release the video capture object and close the display window
    cap.release()
    if args.save_dir is not None:
        output.release()

    producer.close()

    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
