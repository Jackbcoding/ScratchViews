import time
import random as rand
import scratchattach as sa
from datetime import datetime

# Get project ID and view amount from user
projectID = 1147312565 # EDIT THESE TO YOUR OWN PROGECT
viewAmount = 5000

# Estimate time to complete
timeEstimate = ((viewAmount * 80) / 60)
print(timeEstimate)
# Initialize session and project
waitTime = 0
session = sa.get_user("griffpatch")  # Set this to a user that is NOT the owner of the project you are view boting
project = sa.get_project(projectID) 

# Loop to post views
for i in range(viewAmount):
    try:
        project.post_view()
        print("Posted view #" + str(i + 1) + ".\n" + str(((i + 1) / viewAmount) * 100) + "% done with views.")
        
        if not (i == (viewAmount - 1)):
            waitTime = rand.randint(60, 90)
            print("Waiting " + str(waitTime) + " seconds until next view to prevent being blocked/rate limited by Scratch.")
            print("Estimated time left: " + str(timeEstimate - ((80 * (i + 1)) / 60)) + " minutes")
            time.sleep(waitTime)
    except Exception as e:
        print(f"Error posting view #{i + 1}: {e}")
        break

# Print completion time
current_time = datetime.now().time()
print("Done at " + str(current_time))
Print("h"+1) #Error to end the program
